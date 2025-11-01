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
