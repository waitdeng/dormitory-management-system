"""Check-in application and accommodation query endpoints (spec §6.4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import (
    CurrentUser,
    DbSession,
    get_request_id,
    require_permission,
)
from app.core.permissions import (
    PERM_CHECKIN_ALLOCATE,
    PERM_CHECKIN_APPROVE,
    PERM_CHECKIN_CONFIRM,
    PERM_CHECKIN_CREATE,
    PERM_CHECKIN_VIEW,
)
from app.schemas.accommodation import (
    CheckinApplicationCreate,
    CheckinCancelRequest,
    CheckinConfirmRequest,
    CheckinRejectRequest,
    CheckinReserveRequest,
)
from app.schemas.common import PageEnvelope
from app.services import checkin_service
from app.services.data_scope import resolve_for_principal

router = APIRouter(prefix="/checkin-applications", tags=["checkin"])

ViewApp = Annotated[CurrentUser, Depends(require_permission(PERM_CHECKIN_VIEW))]
CreateApp = Annotated[CurrentUser, Depends(require_permission(PERM_CHECKIN_CREATE))]
ApproveApp = Annotated[CurrentUser, Depends(require_permission(PERM_CHECKIN_APPROVE))]
AllocateApp = Annotated[CurrentUser, Depends(require_permission(PERM_CHECKIN_ALLOCATE))]
ConfirmApp = Annotated[CurrentUser, Depends(require_permission(PERM_CHECKIN_CONFIRM))]


@router.get("", response_model=PageEnvelope)
async def list_applications(
    db: DbSession,
    guard: ViewApp,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, max_length=32),
    employee_id: int | None = Query(None, ge=1),
    keyword: str | None = Query(None, max_length=64),
):
    scope = await resolve_for_principal(db, guard)
    items, total = await checkin_service.list_applications(
        db,
        scope=scope,
        page=page,
        page_size=page_size,
        status=status,
        employee_id=employee_id,
        keyword=keyword,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
async def create_application(
    payload: CheckinApplicationCreate,
    request: Request,
    db: DbSession,
    guard: CreateApp,
):
    return await checkin_service.create_application(
        db,
        employee_id=payload.employee_id,
        application_type=payload.application_type,
        requested_checkin_date=payload.requested_checkin_date,
        reason=payload.reason,
        notes=payload.notes,
        idempotency_key=payload.idempotency_key,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.get("/{app_id}")
async def get_application(app_id: int, db: DbSession, _guard: ViewApp):
    return await checkin_service.get_application(db, app_id)


@router.post("/{app_id}/approve")
async def approve_application(
    app_id: int,
    request: Request,
    db: DbSession,
    guard: ApproveApp,
):
    return await checkin_service.approve_application(
        db,
        app_id,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.post("/{app_id}/reject")
async def reject_application(
    app_id: int,
    payload: CheckinRejectRequest,
    request: Request,
    db: DbSession,
    guard: ApproveApp,
):
    return await checkin_service.reject_application(
        db,
        app_id,
        reason=payload.reason,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.post("/{app_id}/reserve")
async def reserve_bed(
    app_id: int,
    payload: CheckinReserveRequest,
    request: Request,
    db: DbSession,
    guard: AllocateApp,
):
    return await checkin_service.reserve_bed(
        db,
        app_id,
        bed_id=payload.bed_id,
        expires_at=payload.expires_at,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.post("/{app_id}/confirm")
async def confirm_checkin(
    app_id: int,
    payload: CheckinConfirmRequest,
    request: Request,
    db: DbSession,
    guard: ConfirmApp,
):
    return await checkin_service.confirm_checkin(
        db,
        app_id,
        checkin_at=payload.checkin_at,
        notes=payload.notes,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.post("/{app_id}/cancel")
async def cancel_application(
    app_id: int,
    payload: CheckinCancelRequest,
    request: Request,
    db: DbSession,
    guard: ApproveApp,
):
    return await checkin_service.cancel_application(
        db,
        app_id,
        reason=payload.reason,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


# ---- Accommodations (mounted under /accommodations via sibling router) ----

acc_router = APIRouter(prefix="/accommodations", tags=["accommodations"])


@acc_router.get("/active")
async def list_active(
    db: DbSession,
    guard: ViewApp,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    employee_id: int | None = Query(None, ge=1),
    bed_id: int | None = Query(None, ge=1),
    building_id: int | None = Query(None, ge=1),
):
    scope = await resolve_for_principal(db, guard)
    items, total = await checkin_service.list_active_accommodations(
        db,
        scope=scope,
        page=page,
        page_size=page_size,
        employee_id=employee_id,
        bed_id=bed_id,
        building_id=building_id,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@acc_router.get("/history")
async def list_history(
    db: DbSession,
    guard: ViewApp,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    employee_id: int | None = Query(None, ge=1),
    include_active: bool = Query(False),
):
    scope = await resolve_for_principal(db, guard)
    items, total = await checkin_service.list_history(
        db,
        scope=scope,
        page=page,
        page_size=page_size,
        employee_id=employee_id,
        include_active=include_active,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@acc_router.get("/{rec_id}")
async def get_accommodation(rec_id: int, db: DbSession, _guard: ViewApp):
    return await checkin_service.get_accommodation(db, rec_id)
