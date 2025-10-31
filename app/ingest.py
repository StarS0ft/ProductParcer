from typing import Iterable
import csv
import io
import os
import re
import httpx

CSV_INDEX_URL = "https://hefitness.se/csv/"

async def fetch_csv_bytes() -> bytes:
    """
    Order of sources:
      1) CSV_URL env var (direct download)
      2) local products.csv (repo file)
      3) try to find a CSV on https://hefitness.se/csv/
    """
    # 1) environment override
    csv_url = os.getenv("CSV_URL")
    if csv_url:
        async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(csv_url)
            r.raise_for_status()
            return r.content

    # 2) local fallback
    if os.path.exists("products.csv"):
        with open("products.csv", "rb") as f:
            return f.read()

    # 3) scrape index for *.csv, else try common name
    async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = await client.get(CSV_INDEX_URL)
        r.raise_for_status()
        text = r.text
        m = re.search(r'href="([^"]+\.csv)"', text, re.I)
        if m:
            url = m.group(1)
            if not url.startswith("http"):
                if url.startswith("/"):
                    url = "https://hefitness.se" + url
                else:
                    url = CSV_INDEX_URL.rstrip("/") + "/" + url
            r2 = await client.get(url)
            r2.raise_for_status()
            return r2.content

        # final attempt
        r2 = await client.get(CSV_INDEX_URL + "products.csv")
        r2.raise_for_status()
        return r2.content

def parse_semicolon_csv(content: bytes) -> Iterable[dict]:
    s = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(s), delimiter=";")
    if not reader.fieldnames:
        raise RuntimeError("CSV header missing or wrong delimiter; expected semicolons ';'.")
    for row in reader:
        yield row
