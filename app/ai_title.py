import re

def build_ai_prompt(row: dict) -> str:
    return (
        "You are an e-commerce SEO assistant. Improve this product title to be clear, "
        "concise, language-preserving, and include key attributes. Keep Swedish if input is Swedish. "
        "Max 90 chars. No clickbait.\n"
        f"Original title: {row.get('Produktnamn') or row.get('name')}\n"
        f"Manufacturer: {row.get('Tillverkare') or row.get('manufacturer')}\n"
        f"Model: {row.get('Modell') or row.get('model')}\n"
        f"Category: {row.get('Varugrupp') or row.get('category')}\n"
        f"Extra: EAN={row.get('EAN')}, Price={row.get('Pris')}\n"
    )

def heuristic_improve_title(title: str | None) -> str | None:
    if not title:
        return None
    t = re.sub(r"\s+", " ", title).strip()
    t = re.sub(r"\((OBS:.*?kvar)\)", "", t, flags=re.I).strip()
    t = t.replace("Hefitness", "HEfitness").replace(" ;", ";")
    return t[:1].upper() + t[1:]
import os
import json
import httpx

def build_llm_title_prompt(row: dict) -> str:
    # Include as much context as possible, especially URL
    return (
        "Task: Evaluate the product title and suggest an improved one if needed.\n"
        "Return STRICT JSON with fields: "
        '{"name_quality":"OK|weak|missed|cant_generate","suggested_title":null|string}.\n'
        "Rules: keep original language (Swedish if Swedish), concise, <= 90 chars, no clickbait.\n"
        "If title is missing, try to infer from URL and fields. If not enough info, set name_quality=cant_generate.\n"
        f"URL: {row.get('URL') or row.get('url')}\n"
        f"Artnr: {row.get('Artnr') or row.get('artnr')}\n"
        f"Category: {row.get('Varugrupp') or row.get('category')}\n"
        f"Name: {row.get('Produktnamn') or row.get('name')}\n"
        f"Manufacturer: {row.get('Tillverkare') or row.get('manufacturer')}\n"
        f"Model: {row.get('Modell') or row.get('model')}\n"
        f"EAN: {row.get('EAN') or row.get('ean')}\n"
        f"Price: {row.get('Pris') or row.get('price')}\n"
        f"Shipping: {row.get('Frakt') or row.get('shipping')}\n"
        f"Description: {row.get('Beskrivning') or row.get('description_html')}\n"
    )

async def generate_title_suggestion_openai(row: dict, timeout_sec: int = 12):
    """
    Calls OpenAI Chat Completions via REST using httpx.
    Requires env OPENAI_API_KEY. Returns dict or None on any failure.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    prompt = build_llm_title_prompt(row)
    payload = {
        "model": "gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are a precise product title editor. Respond ONLY with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 200
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            # Strict JSON expected per response_format; still guard parsing.
            obj = json.loads(text)
            if isinstance(obj, dict) and "name_quality" in obj:
                return obj
    except Exception:
        return None
    return None
import os, json, httpx, logging
_log = logging.getLogger("title.llm")

def build_llm_title_prompt(row: dict) -> str:
    # Context-rich prompt with URL and all fields. Model must return strict JSON.
    return (
        "Task: Evaluate the product title and suggest an improved one if needed.\n"
        "Return STRICT JSON with fields: "
        '{"name_quality":"OK|weak|missed|cant_generate","suggested_title":null|string}.\n'
        "Rules: keep original language (Swedish if Swedish), concise, <= 90 chars, no clickbait.\n"
        "If title is missing, try to infer from URL and fields. If not enough info, use cant_generate.\n"
        f"URL: {row.get('URL') or row.get('url')}\n"
        f"Artnr: {row.get('Artnr') or row.get('artnr')}\n"
        f"Category: {row.get('Varugrupp') or row.get('category')}\n"
        f"Name: {row.get('Produktnamn') or row.get('name')}\n"
        f"Manufacturer: {row.get('Tillverkare') or row.get('manufacturer')}\n"
        f"Model: {row.get('Modell') or row.get('model')}\n"
        f"EAN: {row.get('EAN') or row.get('ean')}\n"
        f"Price: {row.get('Pris') or row.get('price')}\n"
        f"Shipping: {row.get('Frakt') or row.get('shipping')}\n"
        f"Description: {row.get('Beskrivning') or row.get('description_html')}\n"
    )

async def generate_title_suggestion_openai(row: dict, timeout_sec: int = 12):
    """
    Async call to OpenAI Chat Completions via REST using httpx (no new deps).
    Requires env OPENAI_API_KEY. Returns dict with keys:
      - name_quality: OK|weak|missed|cant_generate
      - suggested_title: str|None
    Returns None on any failure. Logs minimal breadcrumbs to STDOUT.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        _log.info("try_openai: key=no")
        return None

    prompt = build_llm_title_prompt(row)
    payload = {
        "model": "gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are a precise product title editor. Respond ONLY with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 200
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            _log.info("try_openai: key=yes url=%s", (row.get("URL") or row.get("url") or "")[:120])
            r = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            obj = json.loads(text)
            if isinstance(obj, dict) and "name_quality" in obj:
                _log.info("openai_ok")
                return obj
    except Exception as e:
        _log.info("openai_fail")
        return None
    return None


import os, json, httpx, logging
_log = logging.getLogger("title.llm")

def build_llm_title_prompt(row: dict) -> str:
    return (
        "Task: Evaluate the product title and suggest an improved one if needed.\n"
        "Return STRICT JSON with fields: "
        '{"name_quality":"OK|weak|missed|cant_generate","suggested_title":null|string}.\n'
        "Rules: keep original language (Swedish if Swedish), concise, <= 90 chars, no clickbait.\n"
        "If title is missing, try to infer from URL and fields. If not enough info, use cant_generate.\n"
        f"URL: {row.get('URL') or row.get('url')}\n"
        f"Artnr: {row.get('Artnr') or row.get('artnr')}\n"
        f"Category: {row.get('Varugrupp') or row.get('category')}\n"
        f"Name: {row.get('Produktnamn') or row.get('name')}\n"
        f"Manufacturer: {row.get('Tillverkare') or row.get('manufacturer')}\n"
        f"Model: {row.get('Modell') or row.get('model')}\n"
        f"EAN: {row.get('EAN') or row.get('ean')}\n"
        f"Price: {row.get('Pris') or row.get('price')}\n"
        f"Shipping: {row.get('Frakt') or row.get('shipping')}\n"
        f"Description: {row.get('Beskrivning') or row.get('description_html')}\n"
    )

async def generate_title_suggestion_openai(row: dict, timeout_sec: int = 12):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        _log.info("try_openai: key=no")
        return None

    prompt = build_llm_title_prompt(row)
    payload = {
        "model": "gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are a precise product title editor. Respond ONLY with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 200
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            _log.info("try_openai: key=yes url=%s", (row.get("URL") or row.get("url") or "")[:120])
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
