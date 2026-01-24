#playwright_utils.py
from contextlib import contextmanager
from playwright.sync_api import sync_playwright
from .config import X_COOKIE_FILE
import json


def load_x_cookies() -> list[dict]:
    try:
        with open(X_COOKIE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []

    cookies = []
    for entry in raw:
        if "name" not in entry or "value" not in entry:
            continue
        cookies.append({
            "name": entry["name"],
            "value": entry["value"],
            "domain": entry.get("domain", ".x.com"),
            "path": entry.get("path", "/"),
            "secure": bool(entry.get("secure", True)),
            "httpOnly": bool(entry.get("httpOnly", False)),
        })
    return cookies


@contextmanager
def playwright_browser(headless: bool = True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            yield browser
        finally:
            browser.close()
