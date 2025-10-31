import os, re, httpx, csv, io
from typing import Iterable
from html import unescape

CSV_INDEX_URL = "https://hefitness.se/csv/"

async def fetch_csv_bytes() -> bytes:
    url = os.getenv("CSV_URL", CSV_INDEX_URL)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False,
                                 headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = await client.get(url)
        r.raise_for_status()
        html = r.text

    # extract body only
    body = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.I|re.S)
    if not body:
        raise RuntimeError("No <body> tag found")

    text = body.group(1)

    # remove ONLY <pre...> and </pre> tags (not other HTML)
    text = re.sub(r"<pre[^>]*>", "", text, flags=re.I)
    text = re.sub(r"</pre>", "", text, flags=re.I)

    # decode entities (&nbsp;)
    text = unescape(text)

    # now strip leftover html tags (simple)
    text = re.sub(r"<[^>]+>", "", text)

    # normalize newlines
    text = text.replace("\r","").strip()

    return text.encode("utf-8")


def parse_semicolon_csv(content: bytes) -> Iterable[dict]:
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    for row in reader:
        yield {k: (v or "").strip() for k, v in row.items()}
