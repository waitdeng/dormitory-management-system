"""Transfer endpoints (spec §6.5)."""

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
    PERM_TRANSFER_COMPLETE,
    PERM_TRANSFER_CREATE,
    PERM_TRANSFER_VIEW,
)
from app.schemas.accommodation import (
    TransferCancelRequest,
    TransferCreate,
    TransferReserveRequest,
)
from app.schemas.common import PageEnvelope
from app.services import transfer_service
from app.services.data_scope import resolve_for_principal

router = APIRouter(prefix="/transfers", tags=["transfers"])

ViewTr = Annotated[CurrentUser, Depends(require_permission(PERM_TRANSFER_VIEW))]
CreateTr = Annotated[CurrentUser, Depends(require_permission(PERM_TRANSFER_CREATE))]
CompleteTr = Annotated[CurrentUser, Depends(require_permission(PERM_TRANSFER_COMPLETE))]


@router.get("", response_model=PageEnvelope)
async def list_transfers(
    db: DbSession,
    guard: ViewTr,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, max_length=32),
    employee_id: int | None = Query(None, ge=1),
    keyword: str | None = Query(None, max_length=64),
):
    scope = await resolve_for_principal(db, guard)
    items, total = await transfer_service.list_transfers(
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
async def create_transfer(
    payload: TransferCreate,
    request: Request,
    db: DbSession,
    guard: CreateTr,
):
    return await transfer_service.create_transfer(
        db,
        employee_id=payload.employee_id,
        target_bed_id=payload.target_bed_id,
        reason=payload.reason,
        notes=payload.notes,
        idempotency_key=payload.idempotency_key,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.get("/{transfer_id}")
async def get_transfer(transfer_id: int, db: DbSession, _guard: ViewTr):
    return await transfer_service.get_transfer(db, transfer_id)


@router.post("/{transfer_id}/reserve")
async def reserve_target(
    transfer_id: int,
    payload: TransferReserveRequest,
    request: Request,
    db: DbSession,
    guard: CreateTr,
):
    return await transfer_service.reserve_target(
        db,
        transfer_id,
        target_bed_id=payload.target_bed_id,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.post("/{transfer_id}/complete")
async def complete_transfer(
    transfer_id: int,
    request: Request,
    db: DbSession,
    guard: CompleteTr,
):
    return await transfer_service.complete_transfer(
        db,
        transfer_id,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )


@router.post("/{transfer_id}/cancel")
async def cancel_transfer(
    transfer_id: int,
    payload: TransferCancelRequest,
    request: Request,
    db: DbSession,
    guard: CompleteTr,
):
    return await transfer_service.cancel_transfer(
        db,
        transfer_id,
        reason=payload.reason,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
