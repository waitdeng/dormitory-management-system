"""M4 scanner endpoints: reservation expiry + alert scan (manual / scheduled)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import (
    CurrentUser,
    DbSession,
    get_request_id,
    require_any_permission,
)
from app.core.permissions import PERM_BED_MANAGE, PERM_EMPLOYEE_OFFBOARD
from app.services import scanner_service as scanner

router = APIRouter(prefix="/scanner", tags=["scanner"])

RunScan = Annotated[
    CurrentUser,
    Depends(require_any_permission(PERM_EMPLOYEE_OFFBOARD, PERM_BED_MANAGE)),
]


@router.post("/run")
async def run_scans(
    db: DbSession,
    principal: RunScan,
    request_id: str = Depends(get_request_id),
):
    """Run reservation expiry + abnormal alert scans (idempotent)."""
    return await scanner.run_all_scans(
        db, actor_user_id=principal.id, request_id=request_id
    )


@router.post("/expire-reservations")
async def expire_reservations(
    db: DbSession,
    principal: RunScan,
    request_id: str = Depends(get_request_id),
):
    return await scanner.expire_reservations(
        db, actor_user_id=principal.id, request_id=request_id
    )


@router.post("/scan-alerts")
async def scan_alerts(
    db: DbSession,
    principal: RunScan,
    request_id: str = Depends(get_request_id),
):
    return await scanner.scan_alerts(
        db, actor_user_id=principal.id, request_id=request_id
    )
