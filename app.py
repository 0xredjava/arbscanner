"""Railway FastAPI entrypoint for the arbitrage scanner."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from services.scan_service import ScanService
from storage.supabase import SupabaseStore
from utils.logging import setup_logging


settings = get_settings()
setup_logging(settings.log_level)
store = SupabaseStore(settings)
scan_service = ScanService(settings, store)


@asynccontextmanager
async def lifespan(_: FastAPI):
    scan_service.start_background()
    yield
    await scan_service.stop_background()


app = FastAPI(title="Arbitrage Scanner API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def require_admin_token(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_TOKEN is not configured",
        )
    if x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )


@app.get("/")
async def root() -> dict:
    return {
        "service": "arbitrage-scanner-api",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/api/health")
async def health() -> dict:
    db = await store.health()
    return {
        "status": "ok" if db.get("ok") else "degraded",
        "database": db,
        "scanner_running": scan_service.is_running,
        "scan_interval_seconds": settings.refresh_interval_seconds,
        "enabled_platforms": settings.enabled_platforms,
    }


@app.get("/api/platforms")
async def platforms() -> dict:
    return {"platforms": await scan_service.latest_platforms()}


@app.get("/api/scans/latest")
async def latest_scan() -> dict:
    latest = await scan_service.latest_scan()
    return {"scan": latest, "running": scan_service.is_running}


@app.get("/api/opportunities/latest")
async def latest_opportunities(
    sport: Annotated[str | None, Query()] = None,
    platform: Annotated[str | None, Query()] = None,
    min_profit: Annotated[float | None, Query(alias="minProfit")] = None,
) -> dict:
    opportunities = await scan_service.latest_opportunities(
        sport=sport,
        platform=platform,
        min_profit=min_profit,
    )
    return {"opportunities": opportunities, "running": scan_service.is_running}


@app.get("/api/opportunities/closest")
async def closest_opportunities(
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict:
    return {
        "comparisons": await scan_service.latest_comparisons(limit=limit),
        "running": scan_service.is_running,
    }


@app.get("/api/events/latest")
async def latest_events(
    platform: Annotated[str | None, Query()] = None,
    sport: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query(alias="q")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 2500,
) -> dict:
    events = await scan_service.latest_events(
        platform=platform,
        sport=sport,
        search=search,
        limit=limit,
    )
    counts: dict[str, int] = {
        enabled_platform: 0 for enabled_platform in settings.enabled_platforms
    }
    for event in events:
        counts[event["platform"]] = counts.get(event["platform"], 0) + 1
    return {
        "scan": await scan_service.latest_scan(),
        "events": events,
        "event_count": len(events),
        "counts_by_platform": counts,
        "running": scan_service.is_running,
        "scan_interval_seconds": settings.refresh_interval_seconds,
    }


@app.post("/api/scans/run", dependencies=[Depends(require_admin_token)])
async def run_scan() -> dict:
    return {"scan": await scan_service.run_scan(trigger="manual")}
