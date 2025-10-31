import re
import httpx

IDENTIFIER_MISSING_PAT = re.compile(r"identifier_exists\s*=\s*no", re.I)

async def check_image_ok(url: str) -> bool:
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

def is_identifier_missing(ean_field: str | None) -> bool:
    if not ean_field or ean_field.strip() in {"-", "0", "None", ""}:
        return True
    if IDENTIFIER_MISSING_PAT.search(ean_field):
        return True
    digits = "".join([c for c in ean_field if c.isdigit()])
    return len(digits) not in (8, 12, 13, 14)
