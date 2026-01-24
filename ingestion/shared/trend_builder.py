#trend_builder.py
import uuid
from datetime import datetime


def build_trend_object(
    *,
    keyword: str,
    category: str,
    trend_type: str = "x_news",
    score: int | None = None,
    region: str = "global",
    summary: str | None = None,
    post_html: str | None = None,
    post_urls: list[str] | None = None,
    url: str | None = None,
) -> dict:
    now = datetime.utcnow().isoformat()

    return {
        "id": str(uuid.uuid4()),
        "keyword": keyword,
        "category": category,
        "trend_type": trend_type,
        "score": score,
        "region": region,
        "summary": summary,
        "post_html": post_html,
        "post_urls": post_urls or [],
        "url": url,
        "ingested_at": now,
        "trend_age": 0,
        "first_seen_at": now,
        "updated_at": now,
    }
