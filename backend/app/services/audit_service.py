"""Audit logging service (append-only)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.base import utcnow


def _jsonable(value: Any) -> Any:
    """Recursively convert values to JSON-safe primitives for audit payloads."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return value


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str | int | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
    before_data: Any = None,
    after_data: Any = None,
    ip_address: str | None = None,
    detail: str | None = None,
) -> AuditLog:
    """Persist an audit entry. Caller owns the outer transaction commit/rollback."""
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        request_id=request_id,
        before_data=_jsonable(before_data),
        after_data=_jsonable(after_data),
        ip_address=ip_address,
        occurred_at=utcnow(),
        detail=detail,
    )
    db.add(entry)
    await db.flush()
    return entry
