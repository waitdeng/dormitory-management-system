"""Health check endpoints (used by Docker healthcheck)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — no DB dependency."""
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "env": settings.APP_ENV,
    }


@router.get("/health/ready")
async def ready(db: DbSession) -> dict:
    """Readiness probe — verifies database connectivity."""
    await db.execute(text("SELECT 1"))
    return {
        "status": "ready",
        "database": "ok",
    }
