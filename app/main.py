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
from .ai_title import heuristic_improve_title, build_ai_prompt
from jinja2 import Environment, FileSystemLoader

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

app = FastAPI(title="AgentMaMa.ai Coding Challenge")
TEMPLATES = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")))

@app.on_event("startup")
def _startup():
    init_db()
    log.info("DB initialized.")

def to_float(v):
    if v is None: return None
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

def is_weak_title(name: str) -> bool:
    t = (name or "").strip()
    if not t:
        return False
    if len(t) < 6:
        return True
    generic = {"produkt", "product", "unknown", "n/a", "na"}
    if t.lower() in generic:
        return True
    # very short alnum code-like strings
    if re.fullmatch(r"[A-Za-z0-9\-_/]{1,8}", t):
        return True
    return False

async def _ingest_impl(session: Session):
    log.info("Starting ingestion...")
    content = await fetch_csv_bytes()
    rows_iter = parse_semicolon_csv(content)
    rows = list(rows_iter)
    log.info(f"Parsed {len(rows)} rows from CSV.")

    def map_row(r):
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

    async def validate_and_build(p_dict):
        p = Product(**p_dict)

        # existing validations (unchanged)
        missing_price = p.price is None or (isinstance(p.price, (int, float)) and p.price <= 0)
        p.missing_price = missing_price
        p.price_status = "missing" if missing_price else "ok"

        missing_id = is_identifier_missing(p.ean or "")
        p.missing_identifier = missing_id
        if not p.ean or p.ean.strip() in {"-", "0", "None", ""}:
            p.ean_status = "missing"
        else:
            p.ean_status = "wrong" if missing_id else "ok"

        ok_img = await check_image_ok(p.image_url)
        p.broken_image = not ok_img
        p.image_status = "ok" if ok_img else "broken"

        # NEW: title validation (no LLM yet)
        if not p.name or not p.name.strip():
            p.name_status = "missed"
        else:
            p.name_status = "weak" if is_weak_title(p.name) else "OK"

        # final result adds title status
        p.validation_result = "OK" if (
            p.price_status == "ok"
            and p.ean_status == "ok"
            and p.image_status == "ok"
            and p.name_status == "OK"
        ) else "ISSUE"

        # unchanged helpers
        p.improved_title = heuristic_improve_title(p.name)
        p.ai_prompt = build_ai_prompt(p_dict["raw"])
        return p

    sem = asyncio.Semaphore(16)
    async def guarded_validate(p_dict):
        async with sem:
            return await validate_and_build(p_dict)

    products = await asyncio.gather(*[guarded_validate(map_row(r)) for r in rows])

    # Clear & insert (unchanged)
    session.exec(text("DELETE FROM product"))
    session.commit()
    for p in products:
        session.add(p)
    session.commit()

    issues = sum(1 for p in products if p.validation_result != "OK")
    example = next((p for p in products if p.improved_title), None)

    return {
        "ingested": len(products),
        "flagged_issues": issues,
        "example_improved_title": example.improved_title if example else None,
        "example_prompt": example.ai_prompt if example else None,
    }

@app.post("/ingest")
async def ingest(session: Session = Depends(get_session)):
    try:
        out = await _ingest_impl(session)
        return JSONResponse(out)
    except Exception as e:
        log.exception("Ingestion failed")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/ingest")
async def ingest_get(session: Session = Depends(get_session)):
    return await ingest(session)

@app.get("/summary")
def summary(session: Session = Depends(get_session)):
    allp = session.exec(select(Product)).all()
    flagged = [p for p in allp if getattr(p, "validation_result", None) != "OK"]
    example = next((p for p in allp if p.improved_title), None)
    return {
        "number_of_products": len(allp),
        "number_flagged_with_issues": len(flagged),
        "example_improved_title": example.improved_title if example else None,
    }

@app.get("/", response_class=HTMLResponse)
def home(session: Session = Depends(get_session)):
    allp = session.exec(select(Product)).all()
    flagged = [p for p in allp if getattr(p, "validation_result", None) != "OK"]
    template = TEMPLATES.get_template("summary.html")
    return template.render(total=len(allp), flagged=len(flagged))
