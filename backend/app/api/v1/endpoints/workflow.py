"""M4 workflow endpoints: todos, alerts, notifications."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select

from app.api.deps import (
    CurrentUser,
    CurrentUserDep,
    DbSession,
    require_any_permission,
)
from app.core.permissions import (
    PERM_CHECKOUT_VIEW,
    PERM_DORM_VIEW,
    PERM_EMPLOYEE_VIEW,
    PERM_REPORT_VIEW,
)
from app.models.workflow import Notification
from app.schemas.common import PageEnvelope
from app.services import workflow_service as wf

router = APIRouter(prefix="/workflow", tags=["workflow"])

# Operational visibility: anyone who can view employees/dorms/checkouts/reports
ViewWorkflow = Annotated[
    CurrentUser,
    Depends(
        require_any_permission(
            PERM_EMPLOYEE_VIEW,
            PERM_DORM_VIEW,
            PERM_CHECKOUT_VIEW,
            PERM_REPORT_VIEW,
        )
    ),
]


@router.get("/todos", response_model=PageEnvelope)
async def list_todos(
    db: DbSession,
    guard: ViewWorkflow,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, max_length=32),
    todo_type: str | None = Query(None, max_length=64),
    business_type: str | None = Query(None, max_length=32),
    employee_id: int | None = Query(None, ge=1),
    assignee_role: str | None = Query(None, max_length=64),
    keyword: str | None = Query(None, max_length=64),
):
    from app.services.data_scope import resolve_for_principal

    scope = await resolve_for_principal(db, guard)
    items, total = await wf.list_todos(
        db,
        page=page,
        page_size=page_size,
        status=status,
        todo_type=todo_type,
        business_type=business_type,
        employee_id=employee_id,
        assignee_role=assignee_role,
        keyword=keyword,
        scope=scope,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/todos/summary")
async def todos_summary(db: DbSession, _guard: ViewWorkflow):
    return await wf.todos_summary(db)


@router.get("/todos/{todo_id}")
async def get_todo(todo_id: int, db: DbSession, _guard: ViewWorkflow):
    return await wf.get_todo(db, todo_id)


@router.post("/todos/{todo_id}/complete")
async def complete_todo(
    todo_id: int,
    db: DbSession,
    principal: CurrentUserDep,
):
    return await wf.complete_todo_by_id(db, todo_id, completed_by=principal.id)


@router.post("/todos/{todo_id}/cancel")
async def cancel_todo(
    todo_id: int,
    db: DbSession,
    principal: CurrentUserDep,
    reason: str | None = Query(None, max_length=255),
):
    return await wf.cancel_todo_by_id(
        db, todo_id, reason=reason, completed_by=principal.id
    )


@router.get("/alerts", response_model=PageEnvelope)
async def list_alerts(
    db: DbSession,
    guard: ViewWorkflow,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query("active", max_length=32),
    alert_type: str | None = Query(None, max_length=64),
    employee_id: int | None = Query(None, ge=1),
    keyword: str | None = Query(None, max_length=64),
):
    from app.services.data_scope import resolve_for_principal

    scope = await resolve_for_principal(db, guard)
    items, total = await wf.list_alerts(
        db,
        page=page,
        page_size=page_size,
        status=status,
        alert_type=alert_type,
        employee_id=employee_id,
        keyword=keyword,
        scope=scope,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/alerts/summary")
async def alerts_summary(db: DbSession, _guard: ViewWorkflow):
    return await wf.alerts_summary(db)


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: int, db: DbSession, _guard: ViewWorkflow):
    return await wf.get_alert(db, alert_id)


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    db: DbSession,
    principal: CurrentUserDep,
    reason: str | None = Query(None, max_length=255),
):
    return await wf.resolve_alert_by_id(
        db, alert_id, reason=reason, resolved_by=principal.id
    )


@router.get("/notifications", response_model=PageEnvelope)
async def list_notifications(
    db: DbSession,
    principal: CurrentUserDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
):
    cond = or_(
        Notification.user_id == principal.id,
        Notification.role_code.in_(principal.roles),
    )
    if unread_only:
        cond = and_(cond, Notification.read_at.is_(None))
    all_ids = (await db.execute(select(Notification.id).where(cond))).scalars().all()
    total_count = len(all_ids)
    page_ids = sorted(all_ids, reverse=True)[
        (page - 1) * page_size : (page - 1) * page_size + page_size
    ]
    if not page_ids:
        return {"items": [], "total": total_count, "page": page, "page_size": page_size}
    rows = (
        await db.execute(select(Notification).where(Notification.id.in_(page_ids)))
    ).scalars().all()
    rows = sorted(rows, key=lambda r: r.id, reverse=True)
    items = [
        {
            "id": r.id,
            "user_id": r.user_id,
            "role_code": r.role_code,
            "category": r.category,
            "title": r.title,
            "content": r.content,
            "business_type": r.business_type,
            "business_id": r.business_id,
            "read_at": r.read_at,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    return {"items": items, "total": total_count, "page": page, "page_size": page_size}
