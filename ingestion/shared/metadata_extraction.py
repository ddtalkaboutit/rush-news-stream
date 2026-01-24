#metadata_extraction.py
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from .text_cleaning import clean_raw_text


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def fetch_html(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:
        return None


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

    byline_clean = None
    for cand in byline_candidates:
        cleaned = cand.strip()
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


def fetch_article_with_metadata(url: str, headline: str, min_chars: int = 400) -> dict | None:
    try:
        article = Article(url)
        article.download()
        article.parse()
        full_text = (article.text or "").strip()
    except Exception as e:
        print(f"[fetch_article_with_metadata] Article fetch failed for {url}: {e}")
        return None

    if not full_text or len(full_text) < min_chars:
        print(f"[fetch_article_with_metadata] Article too short ({len(full_text)} chars) from {url}")
        return None

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
