import os, re, csv, io, httpx
from html import unescape
from typing import Iterable

CSV_INDEX_URL = "https://hefitness.se/csv/"

async def fetch_csv_bytes() -> bytes:
    csv_url = os.getenv("CSV_URL", CSV_INDEX_URL)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent":"Mozilla/5.0"}) as client:
        r = await client.get(csv_url)
        r.raise_for_status()
        html = r.text

    # Extract only the <pre>...</pre> block that contains CSV-like text
    m = re.search(r"<pre[^>]*>(.*?)</pre>", html, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        raise RuntimeError("No <pre> block found at CSV page")

    pre = m.group(1)

    # Strip all HTML tags that are injected inside cells and decode entities
    cleaned = re.sub(r"<.*?>", "", pre)
    cleaned = unescape(cleaned).strip()

    # Basic sanity check
    if "Artnr" not in cleaned or ";" not in cleaned:
        raise RuntimeError("CSV header not detected after cleaning")

    return cleaned.encode("utf-8")

def parse_semicolon_csv(content: bytes) -> Iterable[dict]:
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    for row in reader:
        yield {k: (v or "").strip() for k, v in row.items()}
