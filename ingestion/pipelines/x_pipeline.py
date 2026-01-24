#x_pipeline.py
from urllib.parse import quote
from ingestion.shared.playwright_utils import playwright_browser, load_x_cookies
from ingestion.shared.trend_builder import build_trend_object
from ingestion.shared.sync_client import sync_trends, purge_trends

TABS = {
    "For You": "https://x.com/explore",
    "News": "https://x.com/explore/tabs/news",
    "Entertainment": "https://x.com/explore/tabs/entertainment",
    "Sports": "https://x.com/explore/tabs/sports",
    "Trending": "https://x.com/explore/tabs/trending",
}


def _scroll_page(page, times: int = 6, delay_ms: int = 1500):
    for _ in range(times):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        page.wait_for_timeout(delay_ms)


def _extract_headlines_for_tab(page, category: str, max_items: int):
    print(f"[X] extracting headlines for {category}...")
    items = []
    cards = page.query_selector_all("xpath=//div[@data-testid='trend']")
    total_cards = len(cards)
    print(f"[X] found {total_cards} trend cards in {category}")

    idx = 1
    while len(items) < max_items and idx <= total_cards and idx <= max_items:
        try:
            card = page.query_selector(f"xpath=(//div[@data-testid='trend'])[ {idx} ]")
            if not card:
                idx += 1
                continue

            span = card.query_selector("xpath=.//span")
            headline = span.inner_text().strip() if span else ""
            if not headline or len(headline) < 10:
                idx += 1
                continue

            card.click()
            page.wait_for_timeout(5000)

            topic_url = page.url
            if "/i/trending/" not in topic_url:
                page.go_back()
                page.wait_for_timeout(3000)
                idx += 1
                continue

            items.append(
                {
                    "headline": headline,
                    "url": topic_url,
                    "category": category,
                }
            )

            page.go_back()
            page.wait_for_timeout(3000)

        except Exception as e:
            print(f"[X] Trend {idx} extraction failed: {e}")
            try:
                page.go_back()
                page.wait_for_timeout(3000)
            except Exception:
                pass

        idx += 1

    print(f"[X] final extracted items for {category}: {len(items)}")
    return items


def _extract_trending_topics(page, max_items: int = 15):
    print("[X] extracting flat Trending topics...")
    items = []
    blocks = page.query_selector_all("xpath=//div[@role='link'] | //div[@data-testid='trend']")
    for block in blocks:
        if len(items) >= max_items:
            break
        try:
            text = block.inner_text().strip()
            if not text:
                continue
            topic = text.split("\n")[0].strip()
            if not topic or len(topic) < 2 or topic.isdigit():
                continue
            search_url = f"https://x.com/search?q={quote(topic)}"
            items.append(
                {
                    "headline": topic,
                    "url": search_url,
                    "category": "Trending",
                }
            )
        except Exception:
            continue
    print(f"[X] final extracted Trending topics: {len(items)}")
    return items


def _extract_ai_summary_and_posts(browser, url: str, category: str) -> dict:
    if category == "Trending":
        return {"summary": None, "post_urls": [], "post_html": None}

    context = browser.new_context()
    page = context.new_page()
    try:
        page.goto(url, timeout=60000)
        page.wait_for_timeout(8000)

        timeout_ms = 12000
        poll_interval = 1000
        elapsed = 0
        long_spans = []

        while elapsed < timeout_ms:
            spans = page.query_selector_all("span")
            long_spans = [s for s in spans if len((s.inner_text() or "").strip()) > 200]
            if long_spans:
                break
            page.wait_for_timeout(poll_interval)
            elapsed += poll_interval

        if not long_spans:
            summary_text = "No summary available."
        else:
            spans = page.query_selector_all("span")
            longest_text = ""
            for span in spans:
                try:
                    txt = span.inner_text().strip()
                except Exception:
                    continue
                if txt and len(txt) > len(longest_text):
                    longest_text = txt
            summary_text = longest_text if len(longest_text) >= 200 else "No summary available."

        # TOP posts
        try:
            tabs = page.query_selector_all("div[role='tab']")
            for tab in tabs:
                try:
                    label = (tab.inner_text() or "").strip().lower()
                    if label == "top":
                        tab.click()
                        page.wait_for_timeout(4000)
                        break
                except Exception:
                    continue
        except Exception:
            pass

        _scroll_page(page, times=6, delay_ms=1500)
        articles = page.query_selector_all("article")
        post_urls = []
        for article in articles:
            if len(post_urls) >= 10:
                break
            try:
                links = article.query_selector_all("a")
                for a in links:
                    href = a.get_attribute("href")
                    if href and "/status/" in href:
                        if href.startswith("http"):
                            post_urls.append(href)
                        else:
                            post_urls.append("https://x.com" + href)
                        break
            except Exception:
                continue

        return {
            "summary": summary_text,
            "post_urls": post_urls,
            "post_html": None,
        }

    except Exception as e:
        print("[X] Summary extraction failed:", e)
        return {"summary": "No summary available.", "post_urls": [], "post_html": None}
    finally:
        context.close()


def run_x_pipeline():
    cookies = load_x_cookies()
    all_trends: list[dict] = []

    with playwright_browser(headless=True) as browser:
        context = browser.new_context()
        if cookies:
            context.add_cookies(cookies)
        page = context.new_page()

        # For You
        page.goto(TABS["For You"], timeout=60000)
        page.wait_for_timeout(5000)
        _scroll_page(page)
        for_you_items = _extract_headlines_for_tab(page, "For You", max_items=3)

        # News
        page.goto(TABS["News"], timeout=60000)
        page.wait_for_timeout(5000)
        _scroll_page(page)
        news_items = _extract_headlines_for_tab(page, "News", max_items=5)

        # Entertainment
        page.goto(TABS["Entertainment"], timeout=60000)
        page.wait_for_timeout(5000)
        _scroll_page(page)
        ent_items = _extract_headlines_for_tab(page, "Entertainment", max_items=5)

        # Sports
        page.goto(TABS["Sports"], timeout=60000)
        page.wait_for_timeout(5000)
        _scroll_page(page)
        sports_items = _extract_headlines_for_tab(page, "Sports", max_items=5)

        # Trending flat topics
        page.goto(TABS["Trending"], timeout=60000)
        page.wait_for_timeout(5000)
        _scroll_page(page)
        trending_items = _extract_trending_topics(page, max_items=15)

        context.close()

        # Build trend objects + summaries/posts
        score_counter: dict[str, int] = {}

        def add_items(items, category: str):
            nonlocal all_trends
            for item in items:
                url = item.get("url")
                if not url:
                    continue

                score_counter.setdefault(category, 0)
                score_counter[category] += 1
                score = score_counter[category]

                summary_block = _extract_ai_summary_and_posts(browser, url, category)

                trend = build_trend_object(
                    keyword=item["headline"],
                    category=category,
                    trend_type="x_news",
                    score=score,
                    region="global",
                    summary=summary_block["summary"],
                    post_html=summary_block["post_html"],
                    post_urls=summary_block["post_urls"],
                    url=url,
                )
                all_trends.append(trend)

        add_items(for_you_items, "For You")
        add_items(news_items, "News")
        add_items(ent_items, "Entertainment")
        add_items(sports_items, "Sports")
        add_items(trending_items, "Trending")

    # TODO: merge/dedupe/trim logic can be ported from your existing x_ingest.py
    # For now, we just purge and sync the fresh set.
    purge_trends(trend_type="x_news", keep_latest=0)
    sync_trends(all_trends)
