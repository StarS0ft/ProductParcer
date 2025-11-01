import asyncio
import logging
import os

from fastapi import Depends, FastAPI, Query  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import text
from sqlmodel import Session  # noqa: E402
from sqlmodel import select

from .ai_title import build_ai_prompt, heuristic_improve_title
from .db import get_session, init_db
from .ingest import fetch_csv_bytes, parse_semicolon_csv
from .models import Product
from .validators import check_image_ok, is_identifier_missing

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

app = FastAPI(title="AgentMaMa.ai Coding Challenge")
TEMPLATES = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates"))
)


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
        p.missing_price = p.price is None or (
            isinstance(p.price, (int, float)) and p.price <= 0
        )
        p.missing_identifier = is_identifier_missing(p.ean or "")
        p.broken_image = not (await check_image_ok(p.image_url))
        p.improved_title = heuristic_improve_title(p.name)
        p.ai_prompt = build_ai_prompt(p_dict["raw"])
        return p

    sem = asyncio.Semaphore(16)

    async def guarded_validate(p_dict):
        async with sem:
            return await validate_and_build(p_dict)

    products = await asyncio.gather(*[guarded_validate(map_row(r)) for r in rows])

    # Clear table safely (works across SQLAlchemy 2.x)
    session.exec(text("DELETE FROM product"))
    session.commit()

    for p in products:
        session.add(p)
    session.commit()

    issues = sum(
        1 for p in products if p.missing_price or p.missing_identifier or p.broken_image
    )
    example = next((p for p in products if p.improved_title), None)

    result = {
        "ingested": len(products),
        "flagged_issues": issues,
        "example_improved_title": example.improved_title if example else None,
        "example_prompt": example.ai_prompt if example else None,
    }
    log.info(f"Ingestion done: {result}")
    return result


@app.post("/ingest")
async def ingest(session: Session = Depends(get_session)):
    try:
        out = await _ingest_impl(session)
        return JSONResponse(out)
    except Exception as e:
        log.exception("Ingestion failed")
        return JSONResponse({"error": str(e)}, status_code=500)


# Convenience for clicks in browser:
@app.get("/ingest")
async def ingest_get(session: Session = Depends(get_session)):
    return await ingest(session)


@app.get("/summary")
def summary(session: Session = Depends(get_session)):
    allp = session.exec(select(Product)).all()
    flagged = [
        p for p in allp if p.missing_price or p.missing_identifier or p.broken_image
    ]
    example = next((p for p in allp if p.improved_title), None)
    return {
        "number_of_products": len(allp),
        "number_flagged_with_issues": len(flagged),
        "example_improved_title": example.improved_title if example else None,
    }


@app.get("/products")
def products(
    has_issues: bool = Query(default=False),
    page: int = 1,
    size: int = 50,
    session: Session = Depends(get_session),
):
    items = session.exec(select(Product)).all()
    if has_issues:
        items = [
            p
            for p in items
            if p.missing_price or p.missing_identifier or p.broken_image
        ]
    start, end = (page - 1) * size, (page - 1) * size + size
    return {
        "page": page,
        "size": size,
        "total": len(items),
        "items": [p.dict() for p in items[start:end]],
    }


@app.get("/", response_class=HTMLResponse)
def home(session: Session = Depends(get_session)):
    allp = session.exec(select(Product)).all()
    flagged = [
        p for p in allp if p.missing_price or p.missing_identifier or p.broken_image
    ]
    template = TEMPLATES.get_template("summary.html")
    return template.render(total=len(allp), flagged=len(flagged))


# ===== UI routes (no DB or logic changes) =====
from fastapi import Depends  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from sqlmodel import Session  # noqa: E402

try:
    # reuse existing objects from your app
    from app.db import get_session
    from app.main import TEMPLATES as _TEMPLATES  # if already created
    from app.models import Product

    TEMPLATES = _TEMPLATES
except Exception:
    # fallback if TEMPLATES is defined here
    pass


@app.get("/ui/products", response_class=HTMLResponse)
def products_page(
    page: int = 1, size: int = 50, session: Session = Depends(get_session)
):
    items = session.exec(select(Product)).all()
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


@app.get("/ui/issues", response_class=HTMLResponse)
def products_with_issues_page(
    page: int = 1, size: int = 50, session: Session = Depends(get_session)
):
    items = session.exec(select(Product)).all()
    items = [
        p
        for p in items
        if getattr(p, "missing_price", False)
        or getattr(p, "missing_identifier", False)
        or getattr(p, "broken_image", False)
    ]
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


# ==============================================
