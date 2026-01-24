#html_pipeline.py
from ingestion.shared.metadata_extraction import fetch_article_with_metadata
from ingestion.shared.story_builder import build_story_object, build_suggestion_objects
from ingestion.shared.text_cleaning import classify_topic, guess_sentiment, generate_bullet_summary
from ingestion.shared.sync_client import sync_stories
from ingestion.shared.metadata_extraction import fetch_html
from bs4 import BeautifulSoup

MAX_SCRAPED_ITEMS_PER_SOURCE = 10

HTML_SOURCES = [
    {
        "base_url": "https://justthenews.com",
        "display_name": "Just The News",
        "source_type": "custom",
        "bias": "Right",
    },
    {
        "base_url": "https://www.washingtonpost.com",
        "display_name": "Washington Post",
        "source_type": "custom",
        "bias": "Left",
    },
    {
        "base_url": "https://www.nytimes.com",
        "display_name": "New York Times",
        "source_type": "custom",
        "bias": "Left",
    },
    # add more static HTML-friendly sources here
]


def _generic_homepage_scrape(
    *,
    base_url: str,
    display_name: str,
    source_type: str,
    bias: str | None,
    max_items: int = MAX_SCRAPED_ITEMS_PER_SOURCE,
) -> list[dict]:
    print(f"=== {display_name} ingestion (HTML) ===")
    stories: list[dict] = []

    html = fetch_html(base_url)
    if not html:
        print(f"[HTML] Failed to fetch {display_name} homepage.")
        return stories

    soup = BeautifulSoup(html, "html.parser")
    links_seen = set()
    count = 0

    for a in soup.find_all("a", href=True):
        if count >= max_items:
            break

        href = a["href"]
        text = (a.get_text(" ", strip=True) or "").strip()
        if not text or len(text) < 40:
            continue

        if href in links_seen:
            continue
        links_seen.add(href)

        if href.startswith("/"):
            url = base_url.rstrip("/") + href
        elif href.startswith("http"):
            url = href
        else:
            continue

        headline = text
        print(f"[HTML] → [{display_name}] {headline}")

        meta = fetch_article_with_metadata(url, headline)
        if not meta:
            print("[HTML]   Skipped — no usable article text/metadata")
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
            source_type=source_type,
            source_name=display_name,
            source_url=url,
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
        stories.append(story)
        count += 1

    print(f"[HTML] Done {display_name}: {count} stories ingested.")
    return stories


def run_html_pipeline():
    all_stories: list[dict] = []
    for src in HTML_SOURCES:
        stories = _generic_homepage_scrape(
            base_url=src["base_url"],
            display_name=src["display_name"],
            source_type=src["source_type"],
            bias=src.get("bias"),
        )
        all_stories.extend(stories)

    suggestions = []
    for s in all_stories:
        suggestions.extend(s.pop("suggestions", []))
    sync_stories(all_stories, suggestions)
