#rss_pipeline.py
import feedparser
from typing import List
from ingestion.shared.story_builder import build_story_object, build_suggestion_objects
from ingestion.shared.text_cleaning import classify_topic, guess_sentiment, generate_bullet_summary
from ingestion.shared.metadata_extraction import fetch_article_with_metadata
from ingestion.shared.sync_client import sync_stories

RSS_SOURCES = [
    {
        "id": "cnn",
        "display": "CNN",
        "rss": "http://rss.cnn.com/rss/cnn_latest.rss",
        "bias": "Left",
    },
    {
        "id": "nbc",
        "display": "NBC News",
        "rss": "https://feeds.nbcnews.com/nbcnews/public/news",
        "bias": "Center-Left",
    },
    {
        "id": "abc",
        "display": "ABC News",
        "rss": "https://abcnews.go.com/abcnews/topstories",
        "bias": "Center-Left",
    },
    {
        "id": "cbs",
        "display": "CBS News",
        "rss": "https://www.cbsnews.com/latest/rss/main",
        "bias": "Center-Left",
    },
]

MAX_RSS_ITEMS_PER_SOURCE = 5


def ingest_rss_sources() -> list[dict]:
    all_stories: list[dict] = []
    print("=== RSS ingestion ===")

    for src in RSS_SOURCES:
        rss_url = src["rss"]
        display = src["display"]
        bias = src.get("bias")

        print(f"[RSS] Fetching from {display} ({rss_url})...")
        try:
            feed = feedparser.parse(rss_url)
        except Exception as e:
            print(f"[RSS] Failed to parse for {display}: {e}")
            continue

        if not feed.entries:
            print(f"[RSS] No entries for {display}")
            continue

        for entry in feed.entries[:MAX_RSS_ITEMS_PER_SOURCE]:
            headline = (entry.get("title") or "").strip()
            link = entry.get("link") or entry.get("id")
            if not headline or not link:
                continue

            print(f"[RSS] → [{display}] {headline}")
            meta = fetch_article_with_metadata(link, headline)
            if not meta:
                print("[RSS]   Skipped — no usable article text/metadata")
                continue

            full_text = meta["full_text"]
            byline = meta.get("byline")
            image_url = meta.get("image_url")

            topic = classify_topic(full_text or headline)
            sentiment = guess_sentiment(full_text or headline)
            short_summary = generate_bullet_summary(full_text, 3)
            long_summary = generate_bullet_summary(full_text, 6)

            story = build_story_object(
                headline=headline,
                source_type="rss",
                source_name=display,
                source_url=link,
                topic=topic,
                bias=bias,
                sentiment=sentiment,
                is_breaking=False,
                raw_text=full_text,
                short_summary=short_summary,
                long_summary=long_summary,
                byline=byline,
                image_url=image_url,
            )
            story["suggestions"] = build_suggestion_objects(story["id"], headline, topic)
            all_stories.append(story)

    return all_stories


def run_rss_pipeline():
    stories = ingest_rss_sources()
    suggestions = []
    for s in stories:
        suggestions.extend(s.pop("suggestions", []))
    sync_stories(stories, suggestions)
