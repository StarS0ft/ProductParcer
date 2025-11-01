import csv
import io
import re
from typing import Iterable

import httpx

CSV_INDEX_URL = "https://hefitness.se/csv/"


async def fetch_csv_bytes() -> bytes:
    async with httpx.AsyncClient(timeout=20) as client:
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
        r2 = await client.get(CSV_INDEX_URL + "products.csv")
        r2.raise_for_status()
        return r2.content


def parse_semicolon_csv(content: bytes) -> Iterable[dict]:
    s = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(s), delimiter=";")
    for row in reader:
        yield row
