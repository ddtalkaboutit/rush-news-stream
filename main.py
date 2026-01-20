from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from zoneinfo import ZoneInfo
import traceback
import re
import string
from collections import Counter
import uuid

from database import SessionLocal, engine, Base
import schemas
import models
import config

Base.metadata.create_all(bind=engine)

app = FastAPI(title="News Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ET_TZ = ZoneInfo("America/New_York")


def now_et() -> datetime:
    return datetime.now(ET_TZ)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ============================================================
# /sync (RSS + MS NOW stories)
# ============================================================

@app.post("/sync")
def sync(payload: schemas.SyncPayload, db: Session = Depends(get_db)):
    try:
        if payload.api_key != config.API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")

        # STORIES
        for s in payload.stories:
            story_data = s.dict()
            story_data.pop("first_seen_at", None)
            story_data.pop("updated_at", None)

            existing = (
                db.query(models.Story)
                .filter(models.Story.id == story_data["id"])
                .first()
            )

            if existing:
                for field, value in story_data.items():
                    setattr(existing, field, value)
                existing.updated_at = now_et()
            else:
                new_story = models.Story(
                    **story_data,
                    first_seen_at=now_et(),
                    updated_at=now_et(),
                )
                db.add(new_story)

        # SUGGESTIONS
        for sug in payload.suggestions:
            sug_data = sug.dict()
            sug_data.pop("created_at", None)

            existing_sug = (
                db.query(models.Suggestion)
                .filter(models.Suggestion.id == sug_data["id"])
                .first()
            )

            if existing_sug:
                existing_sug.text = sug_data["text"]
                existing_sug.tone = sug_data["tone"]
            else:
                new_sug = models.Suggestion(
                    **sug_data,
                    created_at=now_et(),
                )
                db.add(new_sug)

        db.commit()

        return {
            "status": "ok",
            "stories_received": len(payload.stories),
            "suggestions_received": len(payload.suggestions),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# /sync_trends (X News + Google Trends)
# ============================================================

@app.post("/sync_trends")
def sync_trends(payload: schemas.SyncTrendsPayload, db: Session = Depends(get_db)):
    try:
        if payload.api_key != config.API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")

        for t in payload.trends:
            trend_data = t.dict()
            trend_data.pop("first_seen_at", None)
            trend_data.pop("updated_at", None)

            # Auto-generate ID if missing (Google Trends)
            if not trend_data.get("id"):
                trend_data["id"] = str(uuid.uuid4())

            existing = (
                db.query(models.Trend)
                .filter(models.Trend.id == trend_data["id"])
                .first()
            )

            if existing:
                for field, value in trend_data.items():
                    setattr(existing, field, value)
                existing.updated_at = now_et()
            else:
                new_trend = models.Trend(
                    **trend_data,
                    first_seen_at=now_et(),
                    updated_at=now_et(),
                )
                db.add(new_trend)

        db.commit()

        return {
            "status": "ok",
            "trends_received": len(payload.trends),
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# /purge_trends
# ============================================================

@app.post("/purge_trends")
def purge_trends(
    api_key: str,
    keep_latest: int = 24,
    trend_type: str = "x_news",
    db: Session = Depends(get_db)
):
    if api_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    q = (
        db.query(models.Trend)
        .filter(models.Trend.trend_type == trend_type)
        .order_by(models.Trend.first_seen_at.desc())
    )

    all_trends = q.all()
    to_keep = all_trends[:keep_latest]
    keep_ids = {t.id for t in to_keep}

    to_delete = [t for t in all_trends if t.id not in keep_ids]
    for t in to_delete:
        db.delete(t)

    db.commit()

    return {
        "status": "ok",
        "kept": len(to_keep),
        "deleted": len(to_delete),
    }


# ============================================================
# /stories
# ============================================================

@app.get("/stories", response_model=list[schemas.StoryOut])
def list_stories(
    topic: str | None = Query(None),
    is_breaking: bool | None = Query(None),
    after: datetime | None = Query(
        None,
        description="Return stories first seen after this time (interpreted in America/New_York if naive).",
    ),
    limit: int = Query(200, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.Story)
        .options(joinedload(models.Story.suggestions))
        .order_by(models.Story.first_seen_at.desc())
    )

    if topic:
        q = q.filter(models.Story.topic == topic)

    if is_breaking is not None:
        q = q.filter(models.Story.is_breaking == is_breaking)

    if after:
        if after.tzinfo is None:
            after = after.replace(tzinfo=ET_TZ)
        else:
            after = after.astimezone(ET_TZ)

        q = q.filter(models.Story.first_seen_at > after)

    return q.limit(limit).all()


@app.get("/stories/{story_id}", response_model=schemas.StoryOut)
def get_story(story_id: str, db: Session = Depends(get_db)):
    story = (
        db.query(models.Story)
        .options(joinedload(models.Story.suggestions))
        .filter(models.Story.id == story_id)
        .first()
    )
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


# ============================================================
# /trends (all trend types)
# ============================================================

@app.get("/trends", response_model=list[schemas.TrendOut])
def list_trends(
    trend_type: str | None = Query(None),
    category: str | None = Query(None),
    region: str | None = Query(None),
    limit: int = Query(200, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(models.Trend).order_by(models.Trend.first_seen_at.desc())

    if trend_type:
        q = q.filter(models.Trend.trend_type == trend_type)

    if category:
        q = q.filter(models.Trend.category == category)

    if region:
        q = q.filter(models.Trend.region == region)

    return q.limit(limit).all()


# ============================================================
# /xtrends (X News only)
# ============================================================

@app.get("/xtrends", response_model=list[schemas.TrendOut])
def list_x_trends(
    limit: int = Query(200, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.Trend)
        .filter(models.Trend.trend_type == "x_news")
        .order_by(models.Trend.first_seen_at.desc())
    )
    return q.limit(limit).all()


# ============================================================
# X TRENDING TOPICS (clustered X NEWS)
# ============================================================

def _get_x_trends_by_category(db: Session, category: str, limit: int):
    q = (
        db.query(models.Trend)
        .filter(
            models.Trend.trend_type == "x_news",
            models.Trend.category == category,
        )
        .order_by(
            models.Trend.score.desc(),
            models.Trend.first_seen_at.desc(),
        )
    )
    return q.limit(limit).all()


@app.get("/xtrending_topics")
def list_x_trending_topics(
    db: Session = Depends(get_db),
):
    for_you_trends = _get_x_trends_by_category(db, "For You", 3)
    news_trends = _get_x_trends_by_category(db, "News", 12)
    entertainment_trends = _get_x_trends_by_category(db, "Entertainment", 12)

    def serialize_trend(t: models.Trend) -> dict:
        return schemas.TrendOut.from_orm(t).dict()

    clusters = [
        {
            "cluster_title": "For You",
            "items": [serialize_trend(t) for t in for_you_trends],
        },
        {
            "cluster_title": "News",
            "items": [serialize_trend(t) for t in news_trends],
        },
        {
            "cluster_title": "Entertainment",
            "items": [serialize_trend(t) for t in entertainment_trends],
        },
    ]

    return clusters


# ============================================================
# Trending topics (clustered stories)
# ============================================================

STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "at", "by",
    "with", "from", "as", "is", "are", "was", "were", "be", "this", "that",
    "it", "its", "after", "over", "into", "about", "new"
}


def _normalize_headline(text: str) -> str:
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _headline_keywords(text: str) -> set[str]:
    norm = _normalize_headline(text)
    tokens = norm.split()
    return {
        t for t in tokens
        if t not in STOPWORDS and len(t) > 2
    }


def _cluster_stories(stories):
    clusters: list[list[dict]] = []

    for story in stories:
        headline = story.headline or ""
        kw = _headline_keywords(headline)
        if not kw:
            continue

        placed = False
        for cluster in clusters:
            rep = cluster[0]
            rep_kw = _headline_keywords(rep.headline or "")
            overlap = kw.intersection(rep_kw)
            if len(overlap) >= 2:
                cluster.append(story)
                placed = True
                break

        if not placed:
            clusters.append([story])

    clusters = [c for c in clusters if len(c) > 1]

    def cluster_score(c):
        size = len(c)
        latest = max(s.first_seen_at for s in c if s.first_seen_at is not None)
        return (size, latest)

    clusters.sort(key=cluster_score, reverse=True)
    return clusters


def _cluster_title(cluster: list[models.Story]) -> tuple[str, list[str]]:
    if not cluster:
        return "Trending Topic", []

    most_recent = max(
        cluster,
        key=lambda s: s.first_seen_at or datetime.min.replace(tzinfo=ET_TZ)
    )

    title = most_recent.headline or "Trending Topic"
    keywords = list(_headline_keywords(title))

    return title, keywords


@app.get("/trending_topics")
def list_trending_topics(
    limit_clusters: int = Query(10, ge=1, le=20),
    story_limit: int = Query(200, ge=10, le=500),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.Story)
        .order_by(models.Story.first_seen_at.desc())
    )
    stories = q.limit(story_limit).all()

    if not stories:
        return []

    breaking_stories = [s for s in stories if s.is_breaking]
    non_breaking_stories = [s for s in stories if not s.is_breaking]

    all_clusters = _cluster_stories(non_breaking_stories)

    top_clusters = all_clusters[:limit_clusters]
    other_clusters = all_clusters[limit_clusters:]
    other_stories_raw = [s for cluster in other_clusters for s in cluster]

    result = []

    if breaking_stories:
        breaking_sorted = sorted(
            breaking_stories,
            key=lambda s: s.first_seen_at or datetime.min.replace(tzinfo=ET_TZ),
            reverse=True
        )

        breaking_clean = []
        seen = set()

        for s in breaking_sorted:
            headline = s.headline or ""
            source = (s.source_name or "").strip().lower()
            norm = _normalize_headline(headline)
            key = f"{norm}::{source}"

            if key in seen:
                continue

            seen.add(key)
            breaking_clean.append({
                "id": s.id,
                "headline": s.headline,
                "source_name": s.source_name,
                "first_seen_at": s.first_seen_at,
            })

        result.append({
            "title": "Breaking News",
            "keywords": [],
            "stories": breaking_clean,
        })

    for cluster in top_clusters:
        title, keywords = _cluster_title(cluster)

        cluster_stories = []
        seen = set()

        for s in cluster:
            headline = s.headline or ""
            source = (s.source_name or "").strip().lower()
            norm = _normalize_headline(headline)
            key = f"{norm}::{source}"

            if key in seen:
                continue

            seen.add(key)
            cluster_stories.append({
                "id": s.id,
                "headline": s.headline,
                "source_name": s.source_name,
                "first_seen_at": s.first_seen_at,
            })

        result.append({
            "title": title,
            "keywords": keywords,
            "stories": cluster_stories,
        })

    if other_stories_raw:
        other_seen = set()
        other_clean = []

        for s in other_stories_raw:
            headline = s.headline or ""
            source = (s.source_name or "").strip().lower()
            norm = _normalize_headline(headline)
            key = f"{norm}::{source}"

            if key in other_seen:
                continue

            other_seen.add(key)
            other_clean.append({
                "id": s.id,
                "headline": s.headline,
                "source_name": s.source_name,
                "first_seen_at": s.first_seen_at,
            })

        result.append({
            "title": "Other News",
            "keywords": [],
            "stories": other_clean,
        })

    return result
