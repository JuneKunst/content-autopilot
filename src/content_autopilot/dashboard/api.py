"""Dashboard API endpoints with HTTP Basic Auth."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.requests import Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from content_autopilot.config import settings
from content_autopilot.orchestrator.scheduler import ContentScheduler

log = structlog.get_logger("dashboard.api")

router = APIRouter(prefix="/api", tags=["dashboard"])
security = HTTPBasic()
templates = Jinja2Templates(directory="src/content_autopilot/dashboard/templates")


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.dashboard_password.encode("utf-8"),
    )
    if not (credentials.username == "admin" and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SourceUpdateRequest(BaseModel):
    name: str | None = None
    feed_url: str | None = None
    enabled: bool | None = None
    max_items: int | None = None


class NewSourceRequest(BaseModel):
    feed_url: str
    name: str | None = None


# ---------------------------------------------------------------------------
# Hardcoded stub data (DB integration comes in a later task)
# ---------------------------------------------------------------------------

_SOURCES: list[dict[str, Any]] = [
    {"id": "hn", "name": "Hacker News", "type": "hn", "enabled": True, "max_items": 30},
    {"id": "reddit", "name": "Reddit", "type": "reddit", "enabled": True, "max_items": 25},
    {"id": "github", "name": "GitHub Trending", "type": "github", "enabled": True, "max_items": 20},
    {"id": "youtube", "name": "YouTube", "type": "youtube", "enabled": False, "max_items": 10},
    {"id": "rss", "name": "RSS Feeds", "type": "rss", "enabled": True, "max_items": 50},
]

_pipeline_running = False


async def _run_pipeline_bg() -> None:
    global _pipeline_running
    _pipeline_running = True
    try:
        from content_autopilot.orchestrator.pipeline import Pipeline

        log.info("dashboard.pipeline.start")
        pipeline = Pipeline(dry_run=False)
        await pipeline.run()
        log.info("dashboard.pipeline.done")
    except Exception as exc:
        log.error("dashboard.pipeline.error", error=str(exc))
    finally:
        _pipeline_running = False


_scheduler = ContentScheduler()


# ---------------------------------------------------------------------------
# 1. GET /api/dashboard/overview
# ---------------------------------------------------------------------------


@router.get("/dashboard/overview")
async def get_overview(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Summary stats for the dashboard home page."""
    return {
        "recent_articles": 0,
        "pipeline_status": "running" if _pipeline_running else "idle",
        "sources_count": len([s for s in _SOURCES if s["enabled"]]),
        "today_published": 0,
        "total_published": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# 2. GET /api/articles
# ---------------------------------------------------------------------------


@router.get("/articles")
async def list_articles(
    page: int = 1,
    limit: int = 20,
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Paginated article list."""
    return {"items": [], "total": 0, "page": page, "limit": limit}


# ---------------------------------------------------------------------------
# 3. GET /api/articles/{id}
# ---------------------------------------------------------------------------


@router.get("/articles/{article_id}")
async def get_article(
    article_id: str,
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Article detail by ID."""
    # Stub — DB integration in a later task
    raise HTTPException(status_code=404, detail="Article not found")


# ---------------------------------------------------------------------------
# 4. GET /api/pipeline/runs
# ---------------------------------------------------------------------------


@router.get("/pipeline/runs")
async def list_pipeline_runs(
    limit: int = 20,
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Pipeline run history."""
    return {"items": [], "total": 0, "limit": limit}


# ---------------------------------------------------------------------------
# 5. POST /api/pipeline/run
# ---------------------------------------------------------------------------


@router.post("/pipeline/run", status_code=202)
async def trigger_pipeline_run(
    background_tasks: BackgroundTasks,
    dry_run: bool = False,
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger a manual pipeline run (async, returns immediately)."""
    global _pipeline_running
    if _pipeline_running:
        raise HTTPException(status_code=409, detail="Pipeline already running")

    log.info("dashboard.pipeline.trigger", dry_run=dry_run, user=user)
    background_tasks.add_task(_run_pipeline_bg)
    return {"status": "accepted", "dry_run": dry_run, "message": "Pipeline run started"}


# ---------------------------------------------------------------------------
# 6. GET /api/sources
# ---------------------------------------------------------------------------


@router.get("/sources")
async def list_sources(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """List all configured sources."""
    return {"items": _SOURCES, "total": len(_SOURCES)}


# ---------------------------------------------------------------------------
# 7. PUT /api/sources/{source_id}
# ---------------------------------------------------------------------------


@router.put("/sources/{source_id}")
async def update_source(
    source_id: str,
    body: SourceUpdateRequest,
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Update source configuration."""
    for source in _SOURCES:
        if source["id"] == source_id:
            if body.name is not None:
                source["name"] = body.name
            if body.feed_url is not None:
                source["feed_url"] = body.feed_url
            if body.enabled is not None:
                source["enabled"] = body.enabled
            if body.max_items is not None:
                source["max_items"] = body.max_items
            return {"status": "updated", "source": source}
    raise HTTPException(status_code=404, detail="Source not found")


# ---------------------------------------------------------------------------
# 8. PATCH /api/sources/{source_id}/toggle
# ---------------------------------------------------------------------------


@router.patch("/sources/{source_id}/toggle")
async def toggle_source(
    source_id: str,
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Enable or disable a source."""
    for source in _SOURCES:
        if source["id"] == source_id:
            source["enabled"] = not source["enabled"]
            return {"status": "toggled", "source_id": source_id, "enabled": source["enabled"]}
    raise HTTPException(status_code=404, detail="Source not found")


# ---------------------------------------------------------------------------
# 9. POST /api/sources
# ---------------------------------------------------------------------------


@router.post("/sources", status_code=201)
async def add_source(
    body: NewSourceRequest,
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Add a new RSS feed source."""
    new_id = f"rss_{len(_SOURCES) + 1}"
    new_source: dict[str, Any] = {
        "id": new_id,
        "name": body.name or body.feed_url,
        "type": "rss",
        "feed_url": body.feed_url,
        "enabled": True,
        "max_items": 20,
    }
    _SOURCES.append(new_source)
    log.info("dashboard.source.added", source_id=new_id, feed_url=body.feed_url)
    return {"status": "created", "source": new_source}


# ---------------------------------------------------------------------------
# 10. GET /api/stats
# ---------------------------------------------------------------------------


@router.get("/stats")
async def get_stats(user: str = Depends(get_current_user)) -> dict[str, Any]:
    """Aggregated statistics (token costs, publish counts, subscriber count)."""
    from content_autopilot.publishers.ghost import GhostPublisher

    # Get subscriber count from Ghost
    try:
        ghost_pub = GhostPublisher()
        subscriber_count = await ghost_pub.get_members_count()
    except Exception as e:
        log.error("stats.ghost_members_error", error=str(e))
        subscriber_count = 0

    return {
        "token_costs": {
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "period": "all_time",
        },
        "publish_counts": {
            "ghost": 0,
            "telegram": 0,
            "discord": 0,
            "total": 0,
        },
        "pipeline_runs": {
            "total": 0,
            "successful": 0,
            "failed": 0,
        },
        "subscriber_count": subscriber_count,
    }


# ---------------------------------------------------------------------------
# 11. GET /api/schedule
# ---------------------------------------------------------------------------


@router.get("/schedule")
async def get_schedule(user: str = Depends(get_current_user)) -> dict[str, Any]:
    items = _scheduler.get_queue()
    return {
        "items": [
            {
                "scheduled_at": item.scheduled_at.isoformat(),
                "title": item.article.title_ko,
                "score": item.score,
            }
            for item in items
        ],
        "queue_size": _scheduler.queue_size(),
    }


# ---------------------------------------------------------------------------
# 12. DELETE /api/schedule/{id}
# ---------------------------------------------------------------------------


@router.delete("/schedule/{schedule_id}", status_code=204)
async def cancel_schedule(
    schedule_id: str,
    user: str = Depends(get_current_user),
) -> None:
    """Cancel a scheduled publish."""
    # Stub — scheduler integration in a later task
    log.info("dashboard.schedule.cancel", schedule_id=schedule_id)
    return None


# ---------------------------------------------------------------------------
# Dashboard HTML routes (T22, T23, T24)
# ---------------------------------------------------------------------------


@router.get("/dashboard", include_in_schema=False)
async def dashboard_home(request: Request, user: str = Depends(get_current_user)):
    """Dashboard home page."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/dashboard/articles", include_in_schema=False)
async def dashboard_articles(
    request: Request, page: int = 1, user: str = Depends(get_current_user)
):
    """Articles list page."""
    return templates.TemplateResponse("articles.html", {"request": request, "page": page})


@router.get("/dashboard/articles/{article_id}", include_in_schema=False)
async def dashboard_article_detail(
    request: Request, article_id: int, user: str = Depends(get_current_user)
):
    """Article detail page."""
    return templates.TemplateResponse(
        "article_detail.html", {"request": request, "article_id": article_id}
    )


@router.get("/dashboard/pipeline", include_in_schema=False)
async def dashboard_pipeline(request: Request, user: str = Depends(get_current_user)):
    """Pipeline management page."""
    return templates.TemplateResponse("pipeline.html", {"request": request})


@router.get("/dashboard/sources", include_in_schema=False)
async def dashboard_sources(request: Request, user: str = Depends(get_current_user)):
    """Sources management page."""
    return templates.TemplateResponse("sources.html", {"request": request})


@router.get("/dashboard/analytics", include_in_schema=False)
async def dashboard_analytics(request: Request, user: str = Depends(get_current_user)):
    """Analytics and monitoring page."""
    return templates.TemplateResponse("analytics.html", {"request": request})


@router.get("/dashboard/monetization", include_in_schema=False)
async def dashboard_monetization(
    request: Request, user: str = Depends(get_current_user)
):
    """Monetization settings page."""
    try:
        import yaml

        with open("config/monetization.yaml") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        log.debug("monetization_config_load_failed", error=str(e))
        config = {}
    return templates.TemplateResponse(
        "analytics.html", {"request": request, "monetization": config}
    )
