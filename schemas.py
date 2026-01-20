from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# -----------------------------
# Suggestion Schemas
# -----------------------------

class SuggestionBase(BaseModel):
    id: str
    story_id: str
    tone: str
    text: str
    created_at: Optional[datetime] = None


class SuggestionCreate(SuggestionBase):
    pass


class SuggestionOut(SuggestionBase):
    model_config = ConfigDict(from_attributes=True)


# -----------------------------
# Story Schemas
# -----------------------------

class StoryBase(BaseModel):
    id: str
    source_type: str
    source_name: Optional[str] = None
    source_url: Optional[str] = None

    headline: str
    raw_text: Optional[str] = None

    short_summary: Optional[str] = None
    long_summary: Optional[str] = None

    topic: Optional[str] = None
    bias_guess: Optional[str] = None
    sentiment: Optional[str] = None

    is_breaking: bool = False

    byline: Optional[str] = None
    image_url: Optional[str] = None

    first_seen_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class StoryCreate(StoryBase):
    pass


class StoryOut(StoryBase):
    suggestions: List[SuggestionOut] = []
    model_config = ConfigDict(from_attributes=True)


# -----------------------------
# Trend Schemas
# -----------------------------

class TrendIn(BaseModel):
    id: Optional[str] = None
    keyword: Optional[str] = None
    category: Optional[str] = None
    trend_type: str
    score: Optional[int] = None
    region: Optional[str] = None
    summary: Optional[str] = None

    post_html: Optional[str] = None
    post_urls: Optional[List[str]] = None
    url: Optional[str] = None

    # Google Trends fields
    title: Optional[str] = None
    search_volume: Optional[str] = None
    percent_change: Optional[str] = None
    status: Optional[str] = None
    started_at: Optional[str] = None

    ingested_at: Optional[datetime] = None
    trend_age: Optional[int] = None

    first_seen_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TrendOut(BaseModel):
    id: str
    keyword: Optional[str] = None
    category: Optional[str] = None
    trend_type: str
    score: Optional[int] = None
    region: Optional[str] = None
    summary: Optional[str] = None

    post_html: Optional[str] = None
    post_urls: Optional[List[str]] = None
    url: Optional[str] = None

    # Google Trends fields
    title: Optional[str] = None
    search_volume: Optional[str] = None
    percent_change: Optional[str] = None
    status: Optional[str] = None
    started_at: Optional[str] = None

    ingested_at: datetime
    trend_age: int

    first_seen_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -----------------------------
# Sync Payload Schemas
# -----------------------------

class SyncPayload(BaseModel):
    api_key: str
    stories: List[StoryCreate]
    suggestions: List[SuggestionCreate]


class SyncTrendsPayload(BaseModel):
    api_key: str
    trends: List[TrendIn]