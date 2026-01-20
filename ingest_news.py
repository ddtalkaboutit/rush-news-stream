"""
News-only ingestion engine for RUSH News Stream

- Fetches RSS stories from major outlets (CNN, NBC, ABC, CBS)
- Scrapes headlines and articles from diverse sources (Fox, NYT, Reuters, AP, WaPo, Just The News, Reduxx, MS NOW)
- Extracts full article text, byline, image
- Cleans, summarizes, classifies
- Generates suggestions
- Syncs stories to backend via /sync
- Runs in a loop every 60 minutes
"""

import uuid
import re
import time
from datetime import datetime
from datetime import timezone
from zoneinfo import ZoneInfo

import unicodedata
import string

import requests
import feedparser
from bs4 import BeautifulSoup
from newspaper import Article
import json
from urllib.parse import quote_plus

import os
from dotenv import load_dotenv

load_dotenv()

# ==============================
# CONFIG: API + SOURCES
# ==============================

API_URL = os.getenv("API_URL", "https://rush-news-stream.onrender.com/sync")
API_KEY = os.getenv("SYNC_API_KEY", "TAi-newsroom")

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

MIN_ARTICLE_CHARS = 400
MAX_RSS_ITEMS_PER_SOURCE = 5
MAX_SCRAPED_ITEMS_PER_SOURCE = 10

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ==============================
# HTML-BASED BYLINE / IMAGE EXTRACTION
# ==============================


def fetch_html(url: str) -> str | None:
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:
        return None


def clean_byline_text(text: str | None) -> str | None:
    if not text:
        return None

    t = text.strip()

    t = re.sub(r"\bshare\b|\bsave\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"Getty Images", "", t, flags=re.IGNORECASE)

    t = re.sub(r"\s+", " ", t).strip()

    return t or None


def extract_byline_and_image(html: str) -> tuple[str | None, str | None]:
    if not html:
        return None, None

    soup = BeautifulSoup(html, "html.parser")

    byline_candidates = []

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or "").lower()
        prop = (meta.get("property") or "").lower()
        if name in ("byl", "byline", "author") or prop in ("article:author",):
            content = (meta.get("content") or "").strip()
            if content:
                byline_candidates.append(content)

    for tag in soup.find_all(True, class_=True):
        class_str = " ".join(tag.get("class") or []).lower()
        if "byline" in class_str or "author" in class_str:
            txt = tag.get_text(" ", strip=True)
            if txt:
                byline_candidates.append(txt)

    byline_clean = None
    for cand in byline_candidates:
        cleaned = clean_byline_text(cand)
        if cleaned and len(cleaned) >= 5:
            byline_clean = cleaned
            break

    image_url = None

    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        image_url = og_img["content"].strip()

    if not image_url:
        img = soup.find("img", src=True)
        if img:
            image_url = img["src"].strip()

    return byline_clean, image_url


# ==============================
# RAW TEXT CLEANING
# ==============================

def clean_raw_text(text: str, headline: str) -> str:
    """
    Cleans raw article text for ALL sources.
    Includes AP-specific removal of social-share junk blocks.
    """

    # AP-specific junk phrases that appear inside article bodies
    ap_junk = [
        "Copy Link copied",
        "Print",
        "Email",
        "X",
        "LinkedIn",
        "Bluesky",
        "Flipboard",
        "Pinterest",
        "Reddit",
        "Read More",
    ]

    lines = [ln.strip() for ln in text.splitlines()]
    cleaned = []

    headline_lower = headline.lower().strip()

    for ln in lines:
        if not ln:
            continue

        ln_lower = ln.lower()

        # Remove AP junk
        if any(junk.lower() in ln_lower for junk in ap_junk):
            continue

        # Remove repeated headline
        if ln_lower == headline_lower:
            continue

        # Remove generic junk
        if any(k in ln_lower for k in ["share", "save", "minutes ago"]):
            continue

        # Remove date-only lines
        if re.match(r"^\d{1,2}\s+\w+\s+\d{4}$", ln):
            continue

        # Remove "12 minutes ago"
        if re.match(r"^\d{1,2}\s+minutes ago$", ln_lower):
            continue

        # Remove "By John Smith"
        if re.match(r"^by\s+[a-z]", ln_lower):
            continue

        cleaned.append(ln)

    return "\n\n".join(cleaned).strip()


# ==============================
# ARTICLE EXTRACTION
# ==============================

def fetch_article_with_metadata(url: str, headline: str) -> dict | None:
    try:
        article = Article(url)
        article.download()
        article.parse()
        full_text = (article.text or "").strip()
    except Exception as e:
        print(f"Article fetch failed for {url}: {e}")
        return None

    if not full_text or len(full_text) < MIN_ARTICLE_CHARS:
        print(f"Article too short ({len(full_text)} chars) from {url}")
        return None

    # Clean text (includes AP cleanup)
    cleaned_text = clean_raw_text(full_text, headline)

    paras = [p.strip() for p in cleaned_text.split("\n") if p.strip()]
    first_paragraph = paras[0] if paras else cleaned_text

    html = fetch_html(url)
    byline, image_url = extract_byline_and_image(html) if html else (None, None)

    return {
        "full_text": cleaned_text,
        "first_paragraph": first_paragraph,
        "byline": byline,
        "image_url": image_url,
    }


# ==============================
# SUMMARIES / TOPIC / SENTIMENT
# ==============================

def _basic_sentence_split(full_text: str) -> list[str]:
    text = full_text.replace("\n", " ").strip()
    parts = re.split(r"\. +", text)
    return [p.strip() for p in parts if p.strip()]


def generate_bullet_summary(full_text: str | None, max_sentences: int) -> str | None:
    if not full_text:
        return None
    sentences = _basic_sentence_split(full_text)
    if not sentences:
        return None
    selected = sentences[:max_sentences]
    return " • " + "\n • ".join(selected)


def clean_summary_against_headline(summary: str | None, headline: str | None) -> str | None:
    if not summary:
        return None
    if not headline:
        return summary

    bullets = [b.strip() for b in summary.split("•") if b.strip()]
    h = headline.lower().strip()

    cleaned = [b for b in bullets if h not in b.lower()]
    if not cleaned:
        return None

    return " • " + "\n • ".join(cleaned)


def generate_short_summary(full_text: str | None, headline: str | None) -> str | None:
    raw = generate_bullet_summary(full_text, 3)
    return clean_summary_against_headline(raw, headline)


def generate_long_summary(full_text: str | None, headline: str | None) -> str | None:
    raw = generate_bullet_summary(full_text, 6)
    return clean_summary_against_headline(raw, headline)


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


# ==============================
# STORY + SUGGESTION OBJECTS
# ==============================

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


# ==============================
# SEND STORIES TO DASHBOARD (/sync)
# ==============================

def send_to_dashboard(stories: list[dict]) -> None:
    payload = {
        "api_key": API_KEY,
        "stories": [],
        "suggestions": []
    }

    for story in stories:
        story_copy = story.copy()
        suggestions = story_copy.pop("suggestions", [])
        payload["stories"].append(story_copy)
        payload["suggestions"].extend(suggestions)

    try:
        print(
            f"Syncing {len(payload['stories'])} stories / "
            f"{len(payload['suggestions'])} suggestions..."
        )
        r = requests.post(API_URL, json=payload, timeout=15)
        r.raise_for_status()
        print("Dashboard sync OK:", r.json())
    except Exception as e:
        print("Dashboard sync FAILED:", e)


# ==============================
# RSS INGESTION (CNN / NBC / ABC / CBS)
# ==============================

def ingest_rss_sources() -> list[dict]:
    all_stories = []
    print("=== RSS ingestion ===")

    for src in RSS_SOURCES:
        rss_url = src["rss"]
        display = src["display"]
        bias = src.get("bias")

        print(f"Fetching RSS from {display} ({rss_url})...")
        try:
            feed = feedparser.parse(rss_url)
        except Exception as e:
            print(f"Failed to parse RSS for {display}: {e}")
            continue

        if not feed.entries:
            print(f"No entries for {display}")
            continue

        count = 0
        for entry in feed.entries[:MAX_RSS_ITEMS_PER_SOURCE]:
            headline = (entry.get("title") or "").strip()
            link = entry.get("link") or entry.get("id")

            if not headline or not link:
                continue

            print(f"→ [{display}] {headline}")
            meta = fetch_article_with_metadata(link, headline)
            if not meta:
                print("   Skipped — no usable article text/metadata")
                continue

            full_text = meta["full_text"]
            byline = meta.get("byline")
            image_url = meta.get("image_url")

            topic = classify_topic(full_text or headline)
            sentiment = guess_sentiment(full_text or headline)
            short_summary = generate_short_summary(full_text, headline)
            long_summary = generate_long_summary(full_text, headline)

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
            count += 1

        print(f"Done {display}: {count} stories ingested.")

    return all_stories


# ==============================
# GENERIC SCRAPER HELPER
# ==============================

def _generic_homepage_scrape(
    *,
    base_url: str,
    display_name: str,
    source_type: str,
    bias: str | None,
    max_items: int = MAX_SCRAPED_ITEMS_PER_SOURCE,
) -> list[dict]:
    print(f"=== {display_name} ingestion ===")
    stories: list[dict] = []

    html = fetch_html(base_url)
    if not html:
        print(f"Failed to fetch {display_name} homepage.")
        return stories

    soup = BeautifulSoup(html, "html.parser")

    links_seen = set()
    count = 0

    for a in soup.find_all("a", href=True):
        if count >= max_items:
            break

        href = a["href"]
        text = (a.get_text(" ", strip=True) or "").strip()

        # Require a reasonably descriptive headline
        if not text or len(text) < 40:
            continue

        if href in links_seen:
            continue
        links_seen.add(href)

        # Normalize URL
        if href.startswith("/"):
            url = base_url.rstrip("/") + href
        elif href.startswith("http"):
            url = href
        else:
            continue

        headline = text
        print(f"→ [{display_name}] {headline}")

        meta = fetch_article_with_metadata(url, headline)
        if not meta:
            print("   Skipped — no usable article text/metadata")
            continue

        full_text = meta["full_text"]
        byline = meta.get("byline")
        image_url = meta.get("image_url")

        topic = classify_topic(full_text or headline)
        sentiment = guess_sentiment(full_text or headline)
        short_summary = generate_short_summary(full_text, headline)
        long_summary = generate_long_summary(full_text, headline)

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

    print(f"Done {display_name}: {count} stories ingested.")
    return stories


# ==============================
# CUSTOM SOURCE: MS NOW (HTML SCRAPE)
# ==============================

def ingest_ms_now() -> list[dict]:
    return _generic_homepage_scrape(
        base_url="https://www.ms.now",
        display_name="MS NOW",
        source_type="custom",
        bias="Left",
        max_items=MAX_SCRAPED_ITEMS_PER_SOURCE,
    )


# ==============================
# FOX NEWS (HTML SCRAPE)
# ==============================

def ingest_fox_news() -> list[dict]:
    return _generic_homepage_scrape(
        base_url="https://www.foxnews.com",
        display_name="Fox News",
        source_type="custom",
        bias="Right",
        max_items=MAX_SCRAPED_ITEMS_PER_SOURCE,
    )


# ==============================
# NEW YORK TIMES (HTML SCRAPE)
# ==============================

def ingest_nytimes() -> list[dict]:
    return _generic_homepage_scrape(
        base_url="https://www.nytimes.com",
        display_name="New York Times",
        source_type="custom",
        bias="Left",
        max_items=MAX_SCRAPED_ITEMS_PER_SOURCE,
    )


# ==============================
# REUTERS (HTML SCRAPE)
# ==============================

def ingest_reuters() -> list[dict]:
    return _generic_homepage_scrape(
        base_url="https://www.reuters.com",
        display_name="Reuters",
        source_type="custom",
        bias="Center",
        max_items=MAX_SCRAPED_ITEMS_PER_SOURCE,
    )


# ==============================
# AP NEWS (HTML SCRAPE)
# ==============================

def ingest_apnews() -> list[dict]:
    return _generic_homepage_scrape(
        base_url="https://apnews.com",
        display_name="AP News",
        source_type="custom",
        bias="Left",
        max_items=MAX_SCRAPED_ITEMS_PER_SOURCE,
    )


# ==============================
# WASHINGTON POST (HTML SCRAPE)
# ==============================

def ingest_washington_post() -> list[dict]:
    return _generic_homepage_scrape(
        base_url="https://www.washingtonpost.com",
        display_name="Washington Post",
        source_type="custom",
        bias="Left",
        max_items=MAX_SCRAPED_ITEMS_PER_SOURCE,
    )


# ==============================
# JUST THE NEWS (HTML SCRAPE)
# ==============================

def ingest_just_the_news() -> list[dict]:
    return _generic_homepage_scrape(
        base_url="https://justthenews.com",
        display_name="Just The News",
        source_type="custom",
        bias="Right",
        max_items=MAX_SCRAPED_ITEMS_PER_SOURCE,
    )


# ==============================
# REDUXX (HTML SCRAPE)
# ==============================

def ingest_reduxx() -> list[dict]:
    return _generic_homepage_scrape(
        base_url="https://reduxx.info",
        display_name="Reduxx",
        source_type="custom",
        bias="Right",
        max_items=MAX_SCRAPED_ITEMS_PER_SOURCE,
    )


# ==============================
# MAIN ENTRYPOINT (NEWS ONLY)
# ==============================

def main():
    start = time.time()
    print("=== News-only ingestion run ====")
    print(f"Start time (UTC): {datetime.utcnow().isoformat()}")

    all_stories: list[dict] = []

    # SCRAPERS FIRST (so they appear UNDER RSS in final ordering)
    reduxx_stories = ingest_reduxx()
    jtn_stories = ingest_just_the_news()
    reuters_stories = ingest_reuters()
    ap_stories = ingest_apnews()
    wapo_stories = ingest_washington_post()
    nyt_stories = ingest_nytimes()
    ms_now_stories = ingest_ms_now()
    fox_stories = ingest_fox_news()

    all_stories.extend(reduxx_stories)
    all_stories.extend(jtn_stories)
    all_stories.extend(reuters_stories)
    all_stories.extend(ap_stories)
    all_stories.extend(wapo_stories)
    all_stories.extend(nyt_stories)
    all_stories.extend(ms_now_stories)
    all_stories.extend(fox_stories)

    # RSS LAST so RSS stories appear at the top of the dashboard
    rss_stories = ingest_rss_sources()
    all_stories.extend(rss_stories)

    print(f"Total stories collected this run: {len(all_stories)}")

    if all_stories:
        send_to_dashboard(all_stories)
    else:
        print("No stories to sync this run.")

    elapsed = time.time() - start
    print(f"Ingestion run complete in {elapsed:.1f} seconds.")


# ADD THE LOOP FOR SCHEDULING (every 60 minutes for news)
import time

if __name__ == "__main__":
    while True:
        main()
        print("Waiting 30 minutes for next run...")
        time.sleep(1800)  # 30 minutes = 1800 seconds
