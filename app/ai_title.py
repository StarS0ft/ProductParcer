import os, re, json, logging, httpx
from html import unescape

_log = logging.getLogger("title.llm")

def _strip_html(text: str) -> str:
    text = unescape(text or "")
    # Remove <script>/<style>
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I|re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I|re.S)
    # Remove all tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text

async def _fetch_url_text(url: str | None, timeout_sec: int = 8, max_chars: int = 2000) -> str:
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return ""
    try:
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            txt = _strip_html(r.text)
            return txt[:max_chars]
    except Exception:
        return ""

def build_assess_prompt(row: dict, page_excerpt: str) -> str:
    return (
        "Task: Evaluate the current product title and, if needed, propose a better one.\n"
        "Return STRICT JSON with fields exactly as: "
        '{"name_quality":"ok|weak|empty|cant_generate","suggested_title":null|string}.\n'
        "Rules:\n"
        "- Use the same language as the input (Swedish stays Swedish).\n"
        "- If current title is missing/blank, set name_quality=empty and generate suggested_title.\n"
        "- If title is present but unclear/low quality, set name_quality=weak and generate suggested_title.\n"
        "- If title is already clear and good, set name_quality=ok and suggested_title=null.\n"
        "- Keep the suggestion concise, <= 90 characters, no clickbait.\n"
        "Available product fields and page excerpt follow.\n\n"
        f"URL: {row.get('URL') or row.get('url')}\n"
        f"Artnr: {row.get('Artnr') or row.get('artnr')}\n"
        f"Category: {row.get('Varugrupp') or row.get('category')}\n"
        f"Title: {row.get('Produktnamn') or row.get('name')}\n"
        f"Manufacturer: {row.get('Tillverkare') or row.get('manufacturer')}\n"
        f"Model: {row.get('Modell') or row.get('model')}\n"
        f"EAN: {row.get('EAN') or row.get('ean')}\n"
        f"Price: {row.get('Pris') or row.get('price')}\n"
        f"Shipping: {row.get('Frakt') or row.get('shipping')}\n"
        f"Description (feed): {row.get('Beskrivning') or row.get('description_html')}\n"
        f"Page excerpt: {page_excerpt}\n"
    )

def heuristic_improve_title(title: str | None) -> str | None:
    if not title:
        return None
    t = re.sub(r"\s+", " ", title).strip()
    t = re.sub(r"\((OBS:.*?kvar)\)", "", t, flags=re.I).strip()
    t = t.replace("Hefitness", "HEfitness").replace(" ;", ";")
    return t[:1].upper() + t[1:] if t else None

async def generate_title_assessment_openai(row: dict, timeout_sec: int = 12):
    """
    Always assess the title. Fetches product page content and asks OpenAI to decide:
      name_quality: ok | weak | empty | cant_generate
      suggested_title: str|null (only when weak/empty)
    Returns dict or None on any failure. Never raises.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        _log.info("try_openai: key=no")
        return None

    url = row.get("URL") or row.get("url")
    excerpt = await _fetch_url_text(url)
    prompt = build_assess_prompt(row, excerpt)

    payload = {
        "model": "gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are a precise product title editor. Respond ONLY with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 220
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            _log.info("try_openai: key=yes url=%s", (url or "")[:120])
            r = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            obj = json.loads(text)
            if isinstance(obj, dict) and "name_quality" in obj:
                _log.info("openai_ok")
                return obj
    except Exception:
        _log.info("openai_fail")
        return None
    return None

# Backwards-compat exports used by main.py
build_ai_prompt = build_assess_prompt
generate_title_suggestion_openai = generate_title_assessment_openai
build_llm_title_prompt = build_assess_prompt