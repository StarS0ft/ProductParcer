"""Validation helpers.
Cleanup only: docstrings and type hints. No behavior changes.
"""
import re
from typing import Optional
import httpx

IDENTIFIER_MISSING_PAT = re.compile(r"identifier_exists\s*=\s*no", re.I)

async def check_image_ok(url: str) -> bool:
    """Return True if the image URL responds successfully; False otherwise."""
    if not url or not url.startswith("http"):
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.head(url)
            if r.status_code >= 400 or r.status_code == 405:
                r = await client.get(url, headers={"Range": "bytes=0-128"})
            return r.status_code < 400
    except Exception:
        return False

def is_identifier_missing(ean_field: Optional[str]) -> bool:
    """Heuristic for missing identifier/EAN. Behavior unchanged."""
    if not ean_field or ean_field.strip() in {"-", "0", "None", ""}:
        return True
    if IDENTIFIER_MISSING_PAT.search(ean_field):
        return True
    digits = "".join([c for c in ean_field if c.isdigit()])
    return len(digits) not in (8, 12, 13, 14)
