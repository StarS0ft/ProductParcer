"""CSV fetching and parsing utilities.
Cleanup only: docstrings and type hints. Behavior unchanged.
"""
import csv
import httpx
import io
import os
import re
from html import unescape
from typing import Iterable, Dict

CSV_INDEX_URL = "https://hefitness.se/csv/"


def _strip_html(text: str) -> str:
    """Remove simple HTML tags and decode entities. Behavior unchanged."""
    text = unescape(text)
    text = re.sub(r"<pre[^>]*>", "", text, flags=re.I)
    text = re.sub(r"</pre>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text


async def fetch_csv_bytes() -> bytes:
    """Fetch CSV-like content from URL or CSV_URL env. Behavior unchanged."""
    url = os.getenv("CSV_URL", CSV_INDEX_URL)
    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        verify=False,  # kept as-is to avoid behavior changes
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        raw = r.text

    # If <body> exists use it, else use whole text. Logic unchanged.
    m = re.search(r"<body[^>]*>(.*?)</body>", raw, flags=re.I | re.S)
    text = m.group(1) if m else raw
    text = _strip_html(text).replace("\r", "").strip()
    return text.encode("utf-8")


def parse_semicolon_csv(content: bytes) -> Iterable[Dict[str, str]]:
    """Parse semicolon-delimited CSV. Keeps only lines that contain semicolons."""
    text = content.decode("utf-8", errors="replace")
    lines = [ln for ln in text.split("\n") if ";" in ln]  # keep only lines with semicolons
    text = "\n".join(lines)
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    for row in reader:
        yield {k: (v or "").strip() for k, v in row.items()}
