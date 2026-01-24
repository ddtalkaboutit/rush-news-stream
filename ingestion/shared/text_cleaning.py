#text_cleaning.py
import re


def clean_raw_text(text: str, headline: str) -> str:
    # Placeholder: we’ll port your existing AP + generic cleanup here.
    lines = [ln.strip() for ln in text.splitlines()]
    cleaned = []
    headline_lower = headline.lower().strip()

    for ln in lines:
        if not ln:
            continue
        ln_lower = ln.lower()
        if ln_lower == headline_lower:
            continue
        cleaned.append(ln)

    return "\n\n".join(cleaned).strip()


def basic_sentence_split(full_text: str) -> list[str]:
    text = full_text.replace("\n", " ").strip()
    parts = re.split(r"\. +", text)
    return [p.strip() for p in parts if p.strip()]


def generate_bullet_summary(full_text: str | None, max_sentences: int) -> str | None:
    if not full_text:
        return None
    sentences = basic_sentence_split(full_text)
    if not sentences:
        return None
    selected = sentences[:max_sentences]
    return " • " + "\n • ".join(selected)


def classify_topic(text: str | None) -> str:
    if not text:
        return "general"
    t = text.lower()
    if any(k in t for k in ["biden", "trump", "senate", "congress", "election"]):
        return "politics"
    if any(k in t for k in ["israel", "gaza", "ukraine", "russia", "china"]):
        return "world"
    if any(k in t for k in ["ai", "tech", "microsoft", "apple", "google"]):
        return "technology"
    if any(k in t for k in ["stock", "market", "inflation", "recession"]):
        return "business"
    if any(k in t for k in ["hurricane", "storm", "flood", "wildfire"]):
        return "weather"
    return "general"


def guess_sentiment(text: str | None) -> str:
    if not text:
        return "neutral"
    t = text.lower()
    if any(k in t for k in ["killed", "dead", "attack", "crash", "lawsuit"]):
        return "negative"
    if any(k in t for k in ["wins", "surges", "record high", "breakthrough"]):
        return "positive"
    return "neutral"
