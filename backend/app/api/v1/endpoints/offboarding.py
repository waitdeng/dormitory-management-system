"""M4 offboarding endpoints (spec §6.2 / §6.7)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import (
    CurrentUser,
    DbSession,
    get_request_id,
    require_permission,
)
from app.core.permissions import PERM_EMPLOYEE_OFFBOARD, PERM_EMPLOYEE_VIEW
from app.schemas.common import PageEnvelope
from app.services import offboarding_service as obs

router = APIRouter(prefix="/offboarding", tags=["offboarding"])
emp_router = APIRouter(prefix="/employees", tags=["employees-offboarding"])

Offboard = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_OFFBOARD))]
ViewEmp = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_VIEW))]


class OffboardingRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    termination_date: date | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class TerminateRequest(OffboardingRequest):
    pass


@emp_router.post("/{employee_id}/offboarding")
async def start_offboarding(
    employee_id: int,
    payload: OffboardingRequest,
    db: DbSession,
    principal: Offboard,
    request_id: str = Depends(get_request_id),
):
    return await obs.start_offboarding(
        db,
        employee_id,
        reason=payload.reason,
        notes=payload.notes,
        termination_date=payload.termination_date,
        idempotency_key=payload.idempotency_key,
        actor_user_id=principal.id,
        request_id=request_id,
    )


@emp_router.post("/{employee_id}/terminate")
async def terminate_employee(
    employee_id: int,
    payload: TerminateRequest,
    db: DbSession,
    principal: Offboard,
    request_id: str = Depends(get_request_id),
):
    return await obs.terminate_employee(
        db,
        employee_id,
        reason=payload.reason,
        notes=payload.notes,
        termination_date=payload.termination_date,
        idempotency_key=payload.idempotency_key,
        actor_user_id=principal.id,
        request_id=request_id,
    )


@emp_router.get("/{employee_id}/status-events")
async def list_status_events(
    employee_id: int,
    db: DbSession,
    _guard: ViewEmp,
):
    return {"items": await obs.list_status_events(db, employee_id)}


@router.get("/pending-checkouts", response_model=PageEnvelope)
async def pending_checkouts(
    db: DbSession,
    _guard: ViewEmp,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = await obs.pending_offboarding_checkouts(
        db, page=page, page_size=page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}
