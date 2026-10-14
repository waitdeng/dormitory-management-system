"""Check-out endpoints (spec §6.6)."""

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
    PERM_CHECKOUT_COMPLETE,
    PERM_CHECKOUT_CREATE,
    PERM_CHECKOUT_INSPECT,
    PERM_CHECKOUT_VIEW,
)
from app.schemas.accommodation import (
    CheckoutCancelRequest,
    CheckoutCreate,
    CheckoutInspectionRequest,
)
from app.schemas.common import PageEnvelope
from app.services import checkout_service
from app.services.data_scope import resolve_for_principal

router = APIRouter(prefix="/checkouts", tags=["checkouts"])

ViewCo = Annotated[CurrentUser, Depends(require_permission(PERM_CHECKOUT_VIEW))]
CreateCo = Annotated[CurrentUser, Depends(require_permission(PERM_CHECKOUT_CREATE))]
InspectCo = Annotated[CurrentUser, Depends(require_permission(PERM_CHECKOUT_INSPECT))]
CompleteCo = Annotated[CurrentUser, Depends(require_permission(PERM_CHECKOUT_COMPLETE))]


@router.get("", response_model=PageEnvelope)
async def list_checkouts(
    db: DbSession,
    guard: ViewCo,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, max_length=32),
    employee_id: int | None = Query(None, ge=1),
    keyword: str | None = Query(None, max_length=64),
):
    scope = await resolve_for_principal(db, guard)
    items, total = await checkout_service.list_checkouts(
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
async def create_checkout(
    payload: CheckoutCreate,
    request: Request,
    db: DbSession,
    guard: CreateCo,
):
    return await checkout_service.create_checkout(
        db,
        employee_id=payload.employee_id,
        checkout_type=payload.checkout_type,
        reason=payload.reason,
        expected_checkout_date=payload.expected_checkout_date,
        notes=payload.notes,
        idempotency_key=payload.idempotency_key,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.get("/{checkout_id}")
async def get_checkout(checkout_id: int, db: DbSession, _guard: ViewCo):
    return await checkout_service.get_checkout(db, checkout_id)


@router.patch("/{checkout_id}/inspection")
async def record_inspection(
    checkout_id: int,
    payload: CheckoutInspectionRequest,
    request: Request,
    db: DbSession,
    guard: InspectCo,
):
    return await checkout_service.record_inspection(
        db,
        checkout_id,
        key_returned=payload.key_returned,
        access_card_returned=payload.access_card_returned,
        belongings_cleared=payload.belongings_cleared,
        room_inspected=payload.room_inspected,
        inspection_notes=payload.inspection_notes,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.post("/{checkout_id}/complete")
async def complete_checkout(
    checkout_id: int,
    request: Request,
    db: DbSession,
    guard: CompleteCo,
):
    return await checkout_service.complete_checkout(
        db,
        checkout_id,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.post("/{checkout_id}/cancel")
async def cancel_checkout(
    checkout_id: int,
    payload: CheckoutCancelRequest,
    request: Request,
    db: DbSession,
    guard: CompleteCo,
):
    return await checkout_service.cancel_checkout(
        db,
        checkout_id,
        reason=payload.reason,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
