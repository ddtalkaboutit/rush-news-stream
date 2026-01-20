from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.sqlite import JSON
from datetime import datetime
from zoneinfo import ZoneInfo

from database import Base

ET_TZ = ZoneInfo("America/New_York")


def now_et():
    return datetime.now(ET_TZ)


# ============================================================
# STORY MODEL
# ============================================================

class Story(Base):
    __tablename__ = "stories"

    id = Column(String, primary_key=True, index=True)
    source_type = Column(String, index=True)
    source_name = Column(String, index=True)
    source_url = Column(Text)

    headline = Column(Text, nullable=False)
    raw_text = Column(Text)

    short_summary = Column(Text)
    long_summary = Column(Text)

    topic = Column(String, index=True)
    bias_guess = Column(String, index=True)
    sentiment = Column(String, index=True)

    is_breaking = Column(Boolean, default=False)

    byline = Column(Text)
    image_url = Column(Text)

    first_seen_at = Column(DateTime(timezone=True), default=now_et)
    updated_at = Column(DateTime(timezone=True), default=now_et)

    suggestions = relationship(
        "Suggestion",
        back_populates="story",
        cascade="all, delete-orphan"
    )


# ============================================================
# SUGGESTION MODEL
# ============================================================

class Suggestion(Base):
    __tablename__ = "suggestions"

    id = Column(String, primary_key=True, index=True)
    story_id = Column(String, ForeignKey("stories.id"), index=True, nullable=False)

    tone = Column(String, index=True)
    text = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), default=now_et)

    story = relationship("Story", back_populates="suggestions")


# ============================================================
# TREND MODEL (X NEWS + GOOGLE TRENDS)
# ============================================================

class Trend(Base):
    __tablename__ = "trends"

    id = Column(String, primary_key=True, index=True)

    # X Trends fields
    keyword = Column(Text, nullable=True, index=True)
    category = Column(String, index=True)
    trend_type = Column(String, index=True)  # "x_news", "google_trends", etc.
    score = Column(Integer)
    region = Column(String, index=True)
    summary = Column(Text)

    # Legacy HTML field
    post_html = Column(Text)

    # List of post URLs extracted from topic page
    post_urls = Column(JSON, nullable=True)

    # Topic page URL
    url = Column(Text)

    # Google Trends fields
    title = Column(Text)              # e.g. "Insurrection Act"
    search_volume = Column(String)    # e.g. "100K+"
    percent_change = Column(String)   # e.g. "+1,200%"
    status = Column(String)           # e.g. "Active"
    started_at = Column(String)       # e.g. "6 hours ago"

    # Existing fields
    ingested_at = Column(DateTime(timezone=True), default=now_et)
    trend_age = Column(Integer, default=0)

    first_seen_at = Column(DateTime(timezone=True), default=now_et)

    updated_at = Column(DateTime(timezone=True), default=now_et)
