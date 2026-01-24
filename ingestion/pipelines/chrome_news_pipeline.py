#chrome_news_pipeline.py
from ingestion.shared.playwright_utils import playwright_browser
from ingestion.shared.story_builder import build_story_object, build_suggestion_objects
from ingestion.shared.text_cleaning import classify_topic, guess_sentiment, generate_bullet_summary
from ingestion.shared.sync_client import sync_stories

CHROME_NEWS_SOURCES = [
    {"name": "OAN", "url": "https://www.oann.com", "bias": "Right"},
    {"name": "SAN", "url": "https://straightarrownews.com", "bias": "Center-Right"},
    {"name": "Morning Brew", "url": "https://www.morningbrew.com", "bias": "Center"},
    {"name": "NewsNation", "url": "https://www.newsnationnow.com", "bias": "Center"},
    {"name": "1440", "url": "https://join1440.com", "bias": "Center"},
    {"name": "MS NOW", "url": "https://www.ms.now", "bias": "Left"},
    {"name": "Reduxx", "url": "https://reduxx.info", "bias": "Right"},
    {"name": "Fox News", "url": "https://www.foxnews.com", "bias": "Right"},
]


def _scrape_source_with_playwright(browser, name: str, url: str, bias: str | None) -> list[dict]:
    print(f"=== {name} ingestion (Playwright) ===")
    stories: list[dict] = []

    context = browser.new_context()
    page = context.new_page()

    try:
        page.goto(url, timeout=60000)
        page.wait_for_timeout(5000)

        # TODO: implement site-specific logic per source
        # For now, this is a placeholder that returns no stories.
        print(f"[ChromeNews] Placeholder scraper for {name} at {url}")

    finally:
        context.close()

    return stories


def run_chrome_news_pipeline():
    all_stories: list[dict] = []

    with playwright_browser(headless=True) as browser:
        for src in CHROME_NEWS_SOURCES:
            stories = _scrape_source_with_playwright(
                browser,
                name=src["name"],
                url=src["url"],
                bias=src.get("bias"),
            )
            all_stories.extend(stories)

    suggestions = []
    for s in all_stories:
        suggestions.extend(s.pop("suggestions", []))
    sync_stories(all_stories, suggestions)
