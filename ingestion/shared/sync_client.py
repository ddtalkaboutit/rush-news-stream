#sync_client.py
import json
import requests
from .config import API_SYNC_STORIES_URL, API_SYNC_TRENDS_URL, API_PURGE_TRENDS_URL, API_KEY


def sync_stories(stories: list[dict], suggestions: list[dict]) -> None:
    if not stories:
        print("[sync_stories] No stories to sync.")
        return

    payload = {
        "api_key": API_KEY,
        "stories": stories,
        "suggestions": suggestions,
    }

    try:
        print(f"[sync_stories] Syncing {len(stories)} stories / {len(suggestions)} suggestions...")
        r = requests.post(API_SYNC_STORIES_URL, json=payload, timeout=120)
        r.raise_for_status()
        print("[sync_stories] OK:", r.text)
    except Exception as e:
        print("[sync_stories] FAILED:", e)


def sync_trends(trends: list[dict]) -> None:
    if not trends:
        print("[sync_trends] No trends to sync.")
        return

    payload = {
        "api_key": API_KEY,
        "trends": trends,
    }

    try:
        print(f"[sync_trends] Syncing {len(trends)} trends...")
        r = requests.post(API_SYNC_TRENDS_URL, json=payload, timeout=60)
        r.raise_for_status()
        print("[sync_trends] OK:", r.text)
    except Exception as e:
        print("[sync_trends] FAILED:", e)


def purge_trends(trend_type: str, keep_latest: int = 0) -> None:
    payload = {
        "api_key": API_KEY,
        "trend_type": trend_type,
        "keep_latest": keep_latest,
    }

    try:
        print(f"[purge_trends] Purging trend_type={trend_type}, keep_latest={keep_latest}...")
        r = requests.post(API_PURGE_TRENDS_URL, json=payload, timeout=30)
        r.raise_for_status()
        print("[purge_trends] OK:", r.text)
    except Exception as e:
        print("[purge_trends] FAILED:", e)
