"""Dashboard endpoints (M5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.permissions import PERM_REPORT_VIEW
from app.services import dashboard_service
from app.services.data_scope import resolve_for_principal

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ViewReport = Annotated[CurrentUser, Depends(require_permission(PERM_REPORT_VIEW))]


@router.get("/summary")
async def dashboard_summary(db: DbSession, guard: ViewReport) -> dict:
    scope = await resolve_for_principal(db, guard)
    return await dashboard_service.dashboard_summary(db, scope=scope)


@router.get("/occupancy")
async def dashboard_occupancy(db: DbSession, guard: ViewReport) -> dict:
    scope = await resolve_for_principal(db, guard)
    return await dashboard_service.dashboard_occupancy(db, scope=scope)


@router.get("/trends")
async def dashboard_trends(
    db: DbSession,
    guard: ViewReport,
    days: int = Query(14, ge=1, le=90),
) -> dict:
    scope = await resolve_for_principal(db, guard)
    return await dashboard_service.dashboard_trends(db, scope=scope, days=days)
