"""Report endpoints (M5). List + Excel export share the same filters and data scope."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.exceptions import ValidationError
from app.core.permissions import PERM_REPORT_EXPORT, PERM_REPORT_VIEW
from app.schemas.common import PageEnvelope
from app.services import report_service
from app.services.data_scope import resolve_for_principal

router = APIRouter(prefix="/reports", tags=["reports"])

ViewReport = Annotated[CurrentUser, Depends(require_permission(PERM_REPORT_VIEW))]
ExportReport = Annotated[CurrentUser, Depends(require_permission(PERM_REPORT_EXPORT))]


@router.get("/accommodations", response_model=PageEnvelope)
async def report_accommodations(
    db: DbSession,
    guard: ViewReport,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = Query(None, max_length=64),
    department_id: int | None = Query(None),
    building_id: int | None = Query(None),
) -> PageEnvelope:
    scope = await resolve_for_principal(db, guard)
    items, total = await report_service.report_accommodations(
        db,
        scope=scope,
        page=page,
        page_size=page_size,
        keyword=keyword,
        department_id=department_id,
        building_id=building_id,
    )
    return PageEnvelope(items=items, total=total, page=page, page_size=page_size)


@router.get("/vacant-beds", response_model=PageEnvelope)
async def report_vacant_beds(
    db: DbSession,
    guard: ViewReport,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    building_id: int | None = Query(None),
    floor_id: int | None = Query(None),
) -> PageEnvelope:
    items, total = await report_service.report_vacant_beds(
        db, page=page, page_size=page_size, building_id=building_id, floor_id=floor_id
    )
    return PageEnvelope(items=items, total=total, page=page, page_size=page_size)


@router.get("/departments", response_model=PageEnvelope)
async def report_departments(
    db: DbSession,
    guard: ViewReport,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PageEnvelope:
    scope = await resolve_for_principal(db, guard)
    items, total = await report_service.report_departments(
        db, scope=scope, page=page, page_size=page_size
    )
    return PageEnvelope(items=items, total=total, page=page, page_size=page_size)


@router.get("/checkin-checkout", response_model=PageEnvelope)
async def report_checkin_checkout(
    db: DbSession,
    guard: ViewReport,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    event_type: str | None = Query(None, pattern="^(checkin|checkout)$"),
) -> PageEnvelope:
    scope = await resolve_for_principal(db, guard)
    items, total = await report_service.report_checkin_checkout(
        db,
        scope=scope,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
        event_type=event_type,
    )
    return PageEnvelope(items=items, total=total, page=page, page_size=page_size)


@router.get("/transfers", response_model=PageEnvelope)
async def report_transfers(
    db: DbSession,
    guard: ViewReport,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = Query(None, max_length=32),
) -> PageEnvelope:
    scope = await resolve_for_principal(db, guard)
    items, total = await report_service.report_transfers(
        db, scope=scope, page=page, page_size=page_size, status=status
    )
    return PageEnvelope(items=items, total=total, page=page, page_size=page_size)


@router.get("/exceptions", response_model=PageEnvelope)
async def report_exceptions(
    db: DbSession,
    guard: ViewReport,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = Query("active", max_length=32),
    alert_type: str | None = Query(None, max_length=64),
) -> PageEnvelope:
    scope = await resolve_for_principal(db, guard)
    items, total = await report_service.report_exceptions(
        db, scope=scope, page=page, page_size=page_size, status=status, alert_type=alert_type
    )
    return PageEnvelope(items=items, total=total, page=page, page_size=page_size)


@router.get("/{report_type}/export")
async def export_report(
    report_type: str,
    db: DbSession,
    guard: ExportReport,
    keyword: str | None = Query(None, max_length=64),
    department_id: int | None = Query(None),
    building_id: int | None = Query(None),
    floor_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    event_type: str | None = Query(None, max_length=32),
    status: str | None = Query(None, max_length=32),
    alert_type: str | None = Query(None, max_length=64),
) -> Response:
    scope = await resolve_for_principal(db, guard)
    filters: dict[str, Any] = {
        "keyword": keyword,
        "department_id": department_id,
        "building_id": building_id,
        "floor_id": floor_id,
        "date_from": date_from,
        "date_to": date_to,
        "event_type": event_type,
        "status": status,
        "alert_type": alert_type,
    }
    try:
        content = await report_service.export_report(db, report_type, scope=scope, **filters)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    filename = f"dms_{report_type}_export.xlsx"
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
