from typing import Iterable
import csv
import io
import os
import re
import httpx

CSV_INDEX_URL = "https://hefitness.se/csv/"

async def _download(client, url: str) -> bytes:
    r = await client.get(url)
    r.raise_for_status()
    return r.content

async def _find_csv_from_index(client, base_url: str) -> bytes:
    # ensure trailing slash
    if not base_url.endswith("/"):
        base_url = base_url + "/"
    html = (await _download(client, base_url)).decode("utf-8", "replace")

    # find first csv-like href (case-insensitive), allow query strings
    m = re.search(r'href=["\']([^"\']+\.csv(?:\?[^"\']*)?)["\']', html, re.I)
    if not m:
        # try upper-case .CSV or text-only autoindex
        m = re.search(r'>([^<]+\.csv(?:\?[^<]*)?)<', html, re.I)
    if not m:
        raise RuntimeError(f"No .csv links found at index {base_url}")

    href = m.group(1)
    if not href.startswith("http"):
        if href.startswith("/"):
            # absolute path on same host
            from urllib.parse import urlsplit
            sp = urlsplit(base_url)
            href = f"{sp.scheme}://{sp.netloc}{href}"
        else:
            href = base_url + href
    return await _download(client, href)

async def fetch_csv_bytes() -> bytes:
    """
    Priority:
      1) CSV_URL env var:
         - if it ends with .csv => download it
         - else treat as index and pick the first .csv link
      2) local products.csv
      3) index at CSV_INDEX_URL
    """
    csv_url = os.getenv("CSV_URL")
    async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=True,
                                 headers={"User-Agent":"Mozilla/5.0"}) as client:
        if csv_url:
            if csv_url.lower().endswith(".csv"):
                return await _download(client, csv_url)
            # treat as index directory
            return await _find_csv_from_index(client, csv_url)

        if os.path.exists("products.csv"):
            with open("products.csv", "rb") as f:
                return f.read()

        # default index crawl
        return await _find_csv_from_index(client, CSV_INDEX_URL)

def parse_semicolon_csv(content: bytes) -> Iterable[dict]:
    s = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(s), delimiter=";")
    if not reader.fieldnames:
        raise RuntimeError("CSV header missing or wrong delimiter; expected semicolons ';'.")
    for row in reader:
        yield row
