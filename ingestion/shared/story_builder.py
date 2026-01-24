#story_builder.py
import uuid
from datetime import datetime


def build_story_object(
    *,
    headline: str,
    source_type: str,
    source_name: str | None = None,
    source_url: str | None = None,
    topic: str | None = None,
    bias: str | None = None,
    sentiment: str | None = None,
    is_breaking: bool = False,
    raw_text: str | None = None,
    short_summary: str | None = None,
    long_summary: str | None = None,
    byline: str | None = None,
    image_url: str | None = None,
) -> dict:
    story_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    return {
        "id": story_id,
        "source_type": source_type,
        "source_name": source_name,
        "source_url": source_url,
        "headline": headline,
        "raw_text": raw_text,
        "short_summary": short_summary,
        "long_summary": long_summary,
        "topic": topic,
        "bias_guess": bias,
        "sentiment": sentiment,
        "is_breaking": is_breaking,
        "byline": byline,
        "image_url": image_url,
        "first_seen_at": now,
        "updated_at": now,
    }


def build_suggestion_objects(story_id: str, headline: str, topic: str | None = None) -> list[dict]:
    base = headline.strip()
    now = datetime.utcnow().isoformat()

    tones = [
        ("neutral", f"{base}"),
        ("skeptical", f"{base} — Are we getting the full story here?"),
        ("analytical", f"{base} — What this really means in context."),
        ("snarky", f"{base} — Well, that escalated quickly."),
    ]

    return [
        {
            "id": str(uuid.uuid4()),
            "story_id": story_id,
            "tone": tone,
            "text": text,
            "created_at": now,
        }
        for tone, text in tones
    ]
