import asyncio
import logging
import os
import re
from fastapi import FastAPI, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import select, Session
from sqlalchemy import text
from .db import init_db, get_session
from .models import Product
from .ingest import fetch_csv_bytes, parse_semicolon_csv
from .validators import is_identifier_missing, check_image_ok
from .ai_title import (
    heuristic_improve_title,
    build_ai_prompt,
    generate_title_assessment_openai,
)
from jinja2 import Environment, FileSystemLoader

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

app = FastAPI(title="AgentMaMa.ai Coding Challenge")
TEMPLATES = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates"))
)

# Simple in-memory progress tracker (resets each import)
PROGRESS = {
    "running": False,
    "total": 0,
    "done": 0,
    "summary": None,
}

@app.on_event("startup")
def _startup():
    init_db()
    log.info("DB initialized.")

def to_float(v):
    if v is None:
        return None
    try:
        s = str(v).replace(" ", "").replace("\u00A0", "").replace(",", ".")
        return float(s)
    except Exception:
        return None

def to_int(v):
    try:
        return int(str(v).split(",")[0].strip())
    except Exception:
        return None

async def _ingest_impl(session: Session):
    log.info("Starting ingestion...")
    content = await fetch_csv_bytes()
    rows_iter = parse_semicolon_csv(content)
    rows = list(rows_iter)
    log.info(f"Parsed {len(rows)} rows from CSV.")

    # init progress
    PROGRESS["running"] = True
    PROGRESS["total"] = len(rows)
    PROGRESS["done"] = 0
    PROGRESS["summary"] = None

    def map_row(r: dict) -> dict:
        return {
            "artnr": r.get("Artnr"),
            "category": r.get("Varugrupp"),
            "name": r.get("Produktnamn"),
            "manufacturer": r.get("Tillverkare"),
            "model": r.get("Modell"),
            "ean": r.get("EAN"),
            "stock": to_int(r.get("Lagersaldo")),
            "price": to_float(r.get("Pris")),
            "campaign": to_int(r.get("Kampanjvara(1/0)")),
            "shipping": to_float(r.get("Frakt")),
            "url": r.get("URL"),
            "image_url": r.get("BildURL"),
            "description_html": r.get("Beskrivning"),
            "raw": r,
        }

    async def validate_and_build(p_dict: dict) -> Product:
        p = Product(**p_dict)

        # price
        missing_price = p.price is None or (
            isinstance(p.price, (int, float)) and p.price <= 0
        )
        p.missing_price = missing_price
        p.price_status = "missing" if missing_price else "ok"

        # identifier (EAN)
        missing_id = is_identifier_missing(p.ean or "")
        p.missing_identifier = missing_id
        if not p.ean or p.ean.strip() in {"-", "0", "None", ""}:
            p.ean_status = "missing"
        else:
            p.ean_status = "wrong" if missing_id else "ok"

        # image
        ok_img = await check_image_ok(p.image_url)
        p.broken_image = not ok_img
        p.image_status = "ok" if ok_img else "broken"

        # helpers (always compute)
        p.improved_title = heuristic_improve_title(p.name)

        # Always ask AI to assess title quality using feed fields + fetched page content.
        try:
            assess = await generate_title_assessment_openai(p_dict["raw"])
        except Exception:
            assess = None

        if assess and isinstance(assess, dict):
            q = (assess.get("name_quality") or "").strip().lower()
            sug = assess.get("suggested_title")
            if q == "ok":
                p.name_status = "OK"
                p.name_suggested = None
            elif q == "weak":
                p.name_status = "weak"
                p.name_suggested = (sug or "").strip()[:1024] if isinstance(sug, str) and sug.strip() else None
            elif q == "empty":
                p.name_status = "empty"
                p.name_suggested = (sug or "").strip()[:1024] if isinstance(sug, str) and sug.strip() else None
            else:
                if not p.name or not str(p.name).strip():
                    p.name_status = "empty"
                    p.name_suggested = None
                else:
                    p.name_status = "OK"
                    p.name_suggested = None
        else:
            # API failed -> fallback based on presence of name only
            if not p.name or not str(p.name).strip():
                p.name_status = "empty"
                p.name_suggested = None
            else:
                p.name_status = "OK"
                p.name_suggested = None

        # overall validation result (after AI decision)
        p.validation_result = (
            "OK"
            if (
                p.price_status == "ok"
                and p.ean_status == "ok"
                and p.image_status == "ok"
                and p.name_status == "OK"
            )
            else "ISSUE"
        )

        return p

    sem = asyncio.Semaphore(8)

    async def guarded_validate(p_dict: dict) -> Product:
        async with sem:
            res = await validate_and_build(p_dict)
            PROGRESS["done"] += 1
            return res

    # Use as_completed to update progress as each item finishes
    tasks = [asyncio.create_task(guarded_validate(map_row(r))) for r in rows]
    products: list[Product] = []
    for fut in asyncio.as_completed(tasks):
        p = await fut
        products.append(p)

    # Clear & insert (unchanged)
    session.exec(text("DELETE FROM product"))
    session.commit()
    for p in products:
        session.add(p)
    session.commit()

    issues = sum(1 for p in products if p.validation_result != "OK")
    example = next((p for p in products if (p.name_status in ("weak","empty") and p.name_suggested)), None)

    out = {
        "ingested": len(products),
        "flagged_issues": issues,
        "example_improved_title": example.name_suggested if example else None,
        "example_old_title": example.name if example else None,
    }

    PROGRESS["summary"] = out
    PROGRESS["running"] = False
    return out

@app.post("/ingest")
async def ingest(session: Session = Depends(get_session)):
    try:
        out = await _ingest_impl(session)
        return JSONResponse(out)
    except Exception as e:
        PROGRESS["running"] = False
        log.exception("Ingestion failed")
        return JSONResponse({"error": str(e)}, status_code=500)

# Convenience GET
@app.get("/ingest")
async def ingest_get(session: Session = Depends(get_session)):
    return await ingest(session)

@app.get("/progress")
def progress():
    # lightweight progress endpoint polled by UI
    return {
        "running": PROGRESS["running"],
        "total": PROGRESS["total"],
        "done": PROGRESS["done"],
        "summary": PROGRESS["summary"],
    }

@app.get("/summary")
def summary(session: Session = Depends(get_session)):
    allp = session.exec(select(Product)).all()
    flagged = [p for p in allp if getattr(p, "validation_result", None) != "OK"]
    example = next((p for p in allp if (p.name_status in ("weak","empty") and p.name_suggested)), None)
    return {
        "number_of_products": len(allp),
        "number_flagged_with_issues": len(flagged),
        "example_improved_title": example.name_suggested if example else None,
        "example_old_title": example.name if example else None,
    }

@app.get("/", response_class=HTMLResponse)
def home(session: Session = Depends(get_session)):
    allp = session.exec(select(Product)).all()
    flagged = [p for p in allp if getattr(p, "validation_result", None) != "OK"]
    template = TEMPLATES.get_template("summary.html")
    return template.render(total=len(allp), flagged=len(flagged))

# ===== UI routes (no DB or logic changes) =====
from fastapi.responses import HTMLResponse as _HTML
from sqlmodel import select as _select

@app.get("/ui/products", response_class=_HTML)
def products_page(
    page: int = 1, size: int = 50, session: Session = Depends(get_session)
):
    items = session.exec(_select(Product)).all()
    total = len(items)
    start, end = (page - 1) * size, (page - 1) * size + size
    template = TEMPLATES.get_template("products.html")
    return template.render(
        items=items[start:end],
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size or 1,
        has_issues=False,
        base_path="/ui/products",
    )

@app.get("/ui/issues", response_class=_HTML)
def products_with_issues_page(
    page: int = 1, size: int = 50, session: Session = Depends(get_session)
):
    items = session.exec(_select(Product)).all()
    items = [p for p in items if getattr(p, "validation_result", None) != "OK"]
    total = len(items)
    start, end = (page - 1) * size, (page - 1) * size + size
    template = TEMPLATES.get_template("products.html")
    return template.render(
        items=items[start:end],
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size or 1,
        has_issues=True,
        base_path="/ui/issues",
    )