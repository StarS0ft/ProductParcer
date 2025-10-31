import os, re, httpx, csv, io
from typing import Iterable
from html import unescape

CSV_INDEX_URL = "https://hefitness.se/csv/"

def _strip_html(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<pre[^>]*>", "", text, flags=re.I)
    text = re.sub(r"</pre>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text

async def fetch_csv_bytes() -> bytes:
    url = os.getenv("CSV_URL", CSV_INDEX_URL)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False,
                                 headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = await client.get(url)
        r.raise_for_status()
        raw = r.text

    # if <body> exists use it, else use whole text
    m = re.search(r"<body[^>]*>(.*?)</body>", raw, flags=re.I|re.S)
    text = m.group(1) if m else raw
    text = _strip_html(text).replace("\r","").strip()
    return text.encode("utf-8")

def parse_semicolon_csv(content: bytes) -> Iterable[dict]:
    text = content.decode("utf-8", errors="replace")
    # keep only lines that contain semicolons
    lines = [ln for ln in text.split("\n") if ";" in ln]
    text = "\n".join(lines)
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    for row in reader:
        yield {k: (v or "").strip() for k, v in row.items()}
