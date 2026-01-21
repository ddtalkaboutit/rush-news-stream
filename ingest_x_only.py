"""
X-only ingestion engine for RUSH News Stream (includes Sports tab)

- Fetches X trending headlines + AI summaries + top posts from:
  - For You, News, Entertainment, Sports tabs on https://x.com/explore
- Merges, dedupes, trims to 12 per category (except For You: 3)
- Purges old X trends and syncs new ones to backend via /sync_trends
"""

import uuid
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import json

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import os
from dotenv import load_dotenv

print("Script started - imports successful")
print("X_COOKIE_JSON length:", len(X_COOKIE_JSON))
print("API_TRENDS_URL:", API_TRENDS_URL)

load_dotenv()

# ==============================
# CONFIG: API + COOKIES
# ==============================

API_TRENDS_URL = os.getenv("API_TRENDS_URL", "https://rush-news-stream.onrender.com/sync_trends")
API_KEY = os.getenv("SYNC_API_KEY", "TAi-newsroom")

# Cookies as env var JSON string (paste from x_cookie.json content)
X_COOKIE_JSON = os.getenv("X_COOKIE_JSON", "[]")

# Eastern Time zone object
ET_TZ = ZoneInfo("America/New_York")

# ==============================
# X SETUP HELPERS (unchanged)
# ==============================

def _x_setup_driver():
    from selenium.webdriver.chrome.service import Service as ChromeService
    from webdriver_manager.chrome import ChromeDriverManager
    import os

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # webdriver-manager downloads ChromeDriver
    driver_path = ChromeDriverManager().install()
    service = ChromeService(executable_path=driver_path)

    # If driver_path fails, log it
    print(f"Using ChromeDriver at: {driver_path}")

    return webdriver.Chrome(service=service, options=options)

def _x_load_cookie_json():
    try:
        raw = json.loads(X_COOKIE_JSON)
    except Exception:
        return []

    cookies = []
    for entry in raw:
        if "name" in entry and "value" in entry:
            cookies.append({
                "name": entry["name"],
                "value": entry["value"],
                "domain": ".x.com"
            })
    return cookies


def _x_inject_cookies(driver, cookies):
    driver.get("https://x.com")
    time.sleep(3)
    for cookie in cookies:
        try:
            driver.add_cookie({
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": ".x.com"
            })
        except Exception:
            try:
                driver.add_cookie({
                    "name": cookie["name"],
                    "value": cookie["value"]
                })
            except Exception:
                pass


def _x_new_driver_with_cookies(cookies):
    driver = _x_setup_driver()
    if cookies:
        _x_inject_cookies(driver, cookies)
    return driver


# ---------------------------------------------------------
# Extract first 10 post URLs from the "Top" tab
# ---------------------------------------------------------
def _x_extract_post_urls(driver):
    print("  → Extracting TOP posts...")

    current_url = driver.current_url
    if "mobile." in current_url:
        fixed = current_url.replace("mobile.", "")
        driver.get(fixed)
        time.sleep(4)

    try:
        tabs = driver.find_elements(By.XPATH, "//div[@role='tab']")
        for tab in tabs:
            try:
                if tab.text.strip().lower() == "top":
                    tab.click()
                    print("     Clicked TOP tab")
                    time.sleep(4)
                    break
            except Exception:
                continue
    except Exception:
        print("     Could not click TOP tab")

    for _ in range(6):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)

    articles = driver.find_elements(By.TAG_NAME, "article")
    print(f"     Found {len(articles)} article nodes")

    post_urls = []

    for article in articles:
        if len(post_urls) >= 10:
            break

        try:
            links = article.find_elements(By.TAG_NAME, "a")
            for a in links:
                href = a.get_attribute("href")
                if href and "/status/" in href:
                    post_urls.append(href)
                    break
        except Exception:
            continue

    print(f"     Extracted {len(post_urls)} post URLs")
    return post_urls


# ---------------------------------------------------------
# Extract headlines + topic URLs (parametrized max_items)
# ---------------------------------------------------------
def _x_extract_headlines(driver, max_items: int) -> list[dict]:
    print("  X: extracting headlines + topic URLs via click navigation...")

    cards = driver.find_elements(By.XPATH, '//div[@data-testid="trend"]')
    total_cards = len(cards)
    print(f"  X: found {total_cards} trend cards")

    items = []
    idx = 1

    while len(items) < max_items and idx <= total_cards and idx <= max_items:
        try:
            card_xpath = f"(//div[@data-testid='trend'])[ {idx} ]"
            card = driver.find_element(By.XPATH, card_xpath)

            span = card.find_element(By.XPATH, './/span')
            headline = span.text.strip()

            if not headline or len(headline) < 10:
                print(f"    Trend {idx}: skipped (headline too short)")
                idx += 1
                continue

            print(f"    Trend {idx}: headline → {headline}")

            card.click()
            time.sleep(5)

            topic_url = driver.current_url
            print(f"    Trend {idx}: topic URL → {topic_url}")

            if "/i/trending/" not in topic_url:
                print(f"    Trend {idx}: skipped (not a trending URL)")
                driver.back()
                time.sleep(3)
                idx += 1
                continue

            items.append({
                "headline": headline,
                "url": topic_url
            })

            driver.back()
            time.sleep(3)

        except Exception as e:
            print(f"    Trend {idx}: extraction failed → {e}")
            try:
                driver.back()
                time.sleep(3)
            except Exception:
                pass

        idx += 1

    print(f"  X: final extracted items: {len(items)}")
    return items


# ---------------------------------------------------------
# Trend object now includes category + post_urls
# ---------------------------------------------------------
def build_trend_object(keyword: str, trend_type: str, score: int, category: str) -> dict:
    now_et = datetime.now(ET_TZ).isoformat()

    return {
        "id": str(uuid.uuid4()),
        "keyword": keyword,
        "category": category,          # "For You" | "News" | "Entertainment" | "Sports"
        "trend_type": trend_type,      # "x_news"
        "score": score,
        "region": "global",
        "summary": None,
        "post_html": None,
        "post_urls": [],
        "ingested_at": now_et,
        "trend_age": 0,
        "first_seen_at": now_et,
        "updated_at": now_et,
    }


# ---------------------------------------------------------
# AI summary extraction
# ---------------------------------------------------------
def fetch_x_ai_summary(topic_url: str, cookies: list[dict]) -> dict:
    print(f"  → Fetching X AI summary from: {topic_url}")

    driver = _x_new_driver_with_cookies(cookies)

    try:
        driver.get(topic_url)
        time.sleep(8)

        timeout = 12
        poll_interval = 1
        elapsed = 0
        long_spans = []

        while elapsed < timeout:
            spans = driver.find_elements(By.TAG_NAME, "span")
            long_spans = [s for s in spans if len(s.text.strip()) > 200]
            if long_spans:
                break
            time.sleep(poll_interval)
            elapsed += poll_interval

        if not long_spans:
            summary_text = "No summary available."
        else:
            spans = driver.find_elements(By.TAG_NAME, "span")
            longest_text = ""
            for span in spans:
                try:
                    txt = span.text.strip()
                except Exception:
                    continue
                if txt and len(txt) > len(longest_text):
                    longest_text = txt

            if not longest_text or len(longest_text) < 200:
                summary_text = "No summary available."
            else:
                summary_text = longest_text

        post_urls = _x_extract_post_urls(driver)

        return {
            "summary": summary_text,
            "post_urls": post_urls,
            "post_html": None
        }

    except Exception as e:
        print("     Summary extraction failed:", e)
        return {
            "summary": "No summary available.",
            "post_urls": [],
            "post_html": None
        }
    finally:
        driver.quit()


# ---------------------------------------------------------
# MAIN X INGESTION FUNCTION (For You + News + Entertainment + Sports)
# ---------------------------------------------------------
def ingest_x_trending_news() -> list[dict]:
    print("=== X News + Entertainment + Sports ingestion ===")
    new_trends: list[dict] = []

    cookies = _x_load_cookie_json()
    if cookies:
        print("  X cookie loaded.")
    else:
        print("  No X cookie found; results may be limited.")

    # FOR You (max 3)
    driver_for_you = _x_new_driver_with_cookies(cookies)
    driver_for_you.get("https://x.com/explore")
    time.sleep(5)
    for_you_items = _x_extract_headlines(driver_for_you, max_items=3)
    driver_for_you.quit()

    # NEWS (max 5)
    driver_news = _x_new_driver_with_cookies(cookies)
    driver_news.get("https://x.com/explore/tabs/news")
    time.sleep(5)
    news_items = _x_extract_headlines(driver_news, max_items=5)
    driver_news.quit()

    # ENTERTAINMENT (max 5)
    driver_ent = _x_new_driver_with_cookies(cookies)
    driver_ent.get("https://x.com/explore/tabs/entertainment")
    time.sleep(5)
    ent_items = _x_extract_headlines(driver_ent, max_items=5)
    driver_ent.quit()

    # SPORTS (max 5) - NEW
    driver_sports = _x_new_driver_with_cookies(cookies)
    driver_sports.get("https://x.com/explore/tabs/sports")
    time.sleep(5)
    sports_items = _x_extract_headlines(driver_sports, max_items=5)
    driver_sports.quit()

    # BUILD TRENDS FOR EACH CATEGORY
    # For You
    for idx, item in enumerate(for_you_items, start=1):
        if "url" not in item or not item["url"]:
            print(f"  [For You] Skipping item with no URL: {item['headline']}")
            continue

        trend = build_trend_object(
            keyword=item["headline"],
            trend_type="x_news",
            score=idx,
            category="For You",
        )

        summary_block = fetch_x_ai_summary(item["url"], cookies)
        trend["summary"] = summary_block["summary"]
        trend["post_urls"] = summary_block["post_urls"]
        trend["url"] = item["url"]

        new_trends.append(trend)

    # News
    for idx, item in enumerate(news_items, start=1):
        if "url" not in item or not item["url"]:
            print(f"  [News] Skipping item with no URL: {item['headline']}")
            continue

        trend = build_trend_object(
            keyword=item["headline"],
            trend_type="x_news",
            score=idx,
            category="News",
        )

        summary_block = fetch_x_ai_summary(item["url"], cookies)
        trend["summary"] = summary_block["summary"]
        trend["post_urls"] = summary_block["post_urls"]
        trend["url"] = item["url"]

        new_trends.append(trend)

    # Entertainment
    for idx, item in enumerate(ent_items, start=1):
        if "url" not in item or not item["url"]:
            print(f"  [Entertainment] Skipping item with no URL: {item['headline']}")
            continue

        trend = build_trend_object(
            keyword=item["headline"],
            trend_type="x_news",
            score=idx,
            category="Entertainment",
        )

        summary_block = fetch_x_ai_summary(item["url"], cookies)
        trend["summary"] = summary_block["summary"]
        trend["post_urls"] = summary_block["post_urls"]
        trend["url"] = item["url"]

        new_trends.append(trend)

    # Sports - NEW
    for idx, item in enumerate(sports_items, start=1):
        if "url" not in item or not item["url"]:
            print(f"  [Sports] Skipping item with no URL: {item['headline']}")
            continue

        trend = build_trend_object(
            keyword=item["headline"],
            trend_type="x_news",
            score=idx,
            category="Sports",
        )

        summary_block = fetch_x_ai_summary(item["url"], cookies)
        trend["summary"] = summary_block["summary"]
        trend["post_urls"] = summary_block["post_urls"]
        trend["url"] = item["url"]

        new_trends.append(trend)

    print(f"New X trends collected this run: {len(new_trends)}")

    # -----------------------------------------------------
    # MERGE WITH EXISTING X TRENDS, DEDUPE, ENFORCE 12 PER CATEGORY (Sports also capped at 12)
    # -----------------------------------------------------
    existing_trends: list[dict] = []
    try:
        resp = requests.get(
            "https://rush-news-stream.onrender.com/xtrends",
            timeout=10
        )
        if resp.ok:
            existing_trends = resp.json() or []
    except Exception as e:
        print("Fetch existing X trends failed:", e)

    combined = []
    for t in existing_trends:
        combined.append(t)
    for t in new_trends:
        combined.append(t)

    deduped_by_key: dict[tuple[str, str], dict] = {}

    def norm_headline(h: str) -> str:
        return (h or "").strip().lower()

    for t in combined:
        key = (norm_headline(t.get("keyword")), t.get("category") or "")
        if key in deduped_by_key:
            existing = deduped_by_key[key]
            existing_ts = existing.get("first_seen_at") or existing.get("updated_at") or ""
            new_ts = t.get("first_seen_at") or t.get("updated_at") or ""
            if new_ts > existing_ts:
                deduped_by_key[key] = t
        else:
            deduped_by_key[key] = t

    per_category: dict[str, list[dict]] = {
        "For You": [],
        "News": [],
        "Entertainment": [],
        "Sports": [],  # NEW
    }

    for t in deduped_by_key.values():
        cat = t.get("category") or ""
        if cat in per_category:
            per_category[cat].append(t)

    def sort_key(t: dict):
        return t.get("first_seen_at") or t.get("updated_at") or ""

    final_trends: list[dict] = []

    for cat, items in per_category.items():
        items_sorted = sorted(items, key=sort_key, reverse=True)
        # For You keeps max 3, others 12
        max_cap = 3 if cat == "For You" else 12
        trimmed = items_sorted[:max_cap]
        final_trends.extend(trimmed)

    print(
        f"Final X trends after merge/dedupe/trim: "
        f"For You={len(per_category['For You'])}, "
        f"News={len(per_category['News'])}, "
        f"Entertainment={len(per_category['Entertainment'])}, "
        f"Sports={len(per_category['Sports'])}"
    )

    # -----------------------------------------------------
    # PURGE ALL EXISTING X TRENDS, THEN SYNC CLEAN SET
    # -----------------------------------------------------
    try:
        requests.post(
            "https://rush-news-stream.onrender.com/purge_trends",
            params={
                "api_key": API_KEY,
                "keep_latest": 0,      # delete all x_news trends
                "trend_type": "x_news",
            },
            timeout=10
        )
    except Exception as e:
        print("Purge failed:", e)

    try:
        requests.post(
            "https://rush-news-stream.onrender.com/sync_trends",
            json={
                "api_key": API_KEY,
                "trends": final_trends,
            },
            timeout=20
        )
    except Exception as e:
        print("Sync failed:", e)

    return final_trends


# ==============================
# MAIN ENTRYPOINT (X ONLY)
# ==============================

def main():
    start = time.time()
    print("Starting ingestion...")
    print("=== X-only ingestion run (with Sports) ===")
    print(f"Start time (UTC): {datetime.utcnow().isoformat()}")

    x_trends = ingest_x_trending_news()
    if x_trends:
        send_trends_to_dashboard(x_trends)

    elapsed = time.time() - start
    print(f"Ingestion run complete in {elapsed:.1f} seconds.")


def send_trends_to_dashboard(trends: list[dict]) -> None:
    if not trends:
        print("No trends to sync this run.")
        return

    payload = {
        "api_key": API_KEY,
        "trends": trends,
    }

    try:
        print("Payload preview:", json.dumps(payload, indent=2))
        print(f"Syncing {len(trends)} trends...")
        r = requests.post(API_TRENDS_URL, json=payload, timeout=15)
        r.raise_for_status()
        print("Trend sync OK:", r.json())
    except Exception as e:
        print("Trend sync FAILED:", e)


# ADD THE LOOP HERE FOR SCHEDULING
import time

if __name__ == "__main__":
    while True:
        main()
        print("Waiting 15 minutes for next run...")
        time.sleep(900)  # 15 minutes = 900 seconds
