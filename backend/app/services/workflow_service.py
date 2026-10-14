"""M4 workflow helpers: todos, alerts, notifications.

Shared by offboarding, scanners and business services so that closing a
checkout or expiring a reservation also closes related to-dos / alerts.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ResourceNotFound
from app.models.base import utcnow
from app.models.employee import Employee
from app.models.workflow import Notification, WorkflowAlert, WorkflowTodo

TODO_STATUS = {"pending", "completed", "cancelled"}
ALERT_STATUS = {"active", "resolved"}

# Default assignee roles for generated to-dos (dorm admin handles physical checkout)
DEFAULT_DORM_ROLE = "dorm_admin"
DEFAULT_HR_ROLE = "hr"


def _todo_out(todo: WorkflowTodo, employee: Employee | None = None) -> dict:
    data = {
        "id": todo.id,
        "todo_type": todo.todo_type,
        "business_type": todo.business_type,
        "business_id": todo.business_id,
        "employee_id": todo.employee_id,
        "assignee_role": todo.assignee_role,
        "assignee_user_id": todo.assignee_user_id,
        "title": todo.title,
        "description": todo.description,
        "status": todo.status,
        "priority": todo.priority,
        "due_at": todo.due_at,
        "completed_at": todo.completed_at,
        "completed_by": todo.completed_by,
        "cancel_reason": todo.cancel_reason,
        "source_event_id": todo.source_event_id,
        "created_at": todo.created_at,
        "updated_at": todo.updated_at,
    }
    if employee is not None:
        data["employee_no"] = employee.employee_no
        data["employee_name"] = employee.full_name
    return data


def _alert_out(alert: WorkflowAlert, employee: Employee | None = None) -> dict:
    data = {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "employee_id": alert.employee_id,
        "bed_id": alert.bed_id,
        "accommodation_id": alert.accommodation_id,
        "business_type": alert.business_type,
        "business_id": alert.business_id,
        "title": alert.title,
        "detail": alert.detail,
        "status": alert.status,
        "fingerprint": alert.fingerprint,
        "detected_at": alert.detected_at,
        "resolved_at": alert.resolved_at,
        "resolved_by": alert.resolved_by,
        "resolve_reason": alert.resolve_reason,
        "created_at": alert.created_at,
        "updated_at": alert.updated_at,
    }
    if employee is not None:
        data["employee_no"] = employee.employee_no
        data["employee_name"] = employee.full_name
    return data


async def _employee_map(db: AsyncSession, ids: set[int]) -> dict[int, Employee]:
    if not ids:
        return {}
    rows = (await db.execute(select(Employee).where(Employee.id.in_(ids)))).scalars().all()
    return {e.id: e for e in rows}


# ---- Todos ----


async def find_pending_todo(
    db: AsyncSession,
    *,
    todo_type: str,
    business_type: str,
    business_id: int | None,
    for_update: bool = False,
) -> WorkflowTodo | None:
    bid = 0 if business_id is None else business_id
    stmt = select(WorkflowTodo).where(
        WorkflowTodo.todo_type == todo_type,
        WorkflowTodo.business_type == business_type,
        WorkflowTodo.status == "pending",
        WorkflowTodo.business_id == bid if bid else WorkflowTodo.business_id.is_(None),
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalars().first()


async def ensure_todo(
    db: AsyncSession,
    *,
    todo_type: str,
    business_type: str,
    business_id: int | None,
    employee_id: int | None = None,
    title: str,
    description: str | None = None,
    assignee_role: str = DEFAULT_DORM_ROLE,
    priority: str = "normal",
    due_at: datetime | None = None,
    source_event_id: str | None = None,
    created_by: int | None = None,
) -> WorkflowTodo:
    """Create a pending to-do if one does not already exist for the business key."""
    existing = await find_pending_todo(
        db,
        todo_type=todo_type,
        business_type=business_type,
        business_id=business_id,
        for_update=True,
    )
    if existing is not None:
        return existing

    todo = WorkflowTodo(
        todo_type=todo_type,
        business_type=business_type,
        business_id=business_id,
        employee_id=employee_id,
        assignee_role=assignee_role,
        title=title,
        description=description,
        status="pending",
        priority=priority,
        due_at=due_at,
        source_event_id=source_event_id,
        created_by=created_by,
    )
    db.add(todo)
    try:
        await db.flush()
    except IntegrityError:
        # concurrent insert of the same open business key — return the winner
        await db.rollback()
        existing = await find_pending_todo(
            db,
            todo_type=todo_type,
            business_type=business_type,
            business_id=business_id,
            for_update=True,
        )
        if existing is None:
            raise ConflictError("Duplicate workflow todo") from None
        return existing
    return todo


async def complete_todo(
    db: AsyncSession,
    todo: WorkflowTodo,
    *,
    completed_by: int | None = None,
) -> WorkflowTodo:
    if todo.status == "completed":
        return todo
    if todo.status == "cancelled":
        raise ConflictError("Todo already cancelled")
    todo.status = "completed"
    todo.completed_at = utcnow()
    todo.completed_by = completed_by
    await db.flush()
    return todo


async def cancel_todo(
    db: AsyncSession,
    todo: WorkflowTodo,
    *,
    reason: str | None = None,
    completed_by: int | None = None,
) -> WorkflowTodo:
    if todo.status == "cancelled":
        return todo
    if todo.status == "completed":
        raise ConflictError("Todo already completed")
    todo.status = "cancelled"
    todo.cancel_reason = reason
    todo.completed_at = utcnow()
    todo.completed_by = completed_by
    await db.flush()
    return todo


async def complete_todos_for_business(
    db: AsyncSession,
    *,
    business_type: str,
    business_id: int,
    completed_by: int | None = None,
    reason: str | None = None,
) -> list[WorkflowTodo]:
    """Auto-close pending to-dos bound to a finished business object."""
    rows = (
        await db.execute(
            select(WorkflowTodo)
            .where(
                WorkflowTodo.business_type == business_type,
                WorkflowTodo.business_id == business_id,
                WorkflowTodo.status == "pending",
            )
            .with_for_update()
        )
    ).scalars().all()
    now = utcnow()
    for todo in rows:
        todo.status = "completed"
        todo.completed_at = now
        todo.completed_by = completed_by
        if reason:
            todo.description = (todo.description or "") + f"\n[auto] {reason}"
    if rows:
        await db.flush()
    return list(rows)


async def complete_todos_for_employee(
    db: AsyncSession,
    *,
    employee_id: int,
    todo_types: tuple[str, ...],
    completed_by: int | None = None,
    reason: str | None = None,
) -> list[WorkflowTodo]:
    rows = (
        await db.execute(
            select(WorkflowTodo)
            .where(
                WorkflowTodo.employee_id == employee_id,
                WorkflowTodo.todo_type.in_(todo_types),
                WorkflowTodo.status == "pending",
            )
            .with_for_update()
        )
    ).scalars().all()
    now = utcnow()
    for todo in rows:
        todo.status = "completed"
        todo.completed_at = now
        todo.completed_by = completed_by
        if reason:
            todo.description = (todo.description or "") + f"\n[auto] {reason}"
    if rows:
        await db.flush()
    return list(rows)


async def list_todos(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    todo_type: str | None = None,
    business_type: str | None = None,
    employee_id: int | None = None,
    assignee_role: str | None = None,
    assignee_user_id: int | None = None,
    keyword: str | None = None,
    scope=None,
) -> tuple[list[dict], int]:
    from app.services.data_scope import apply_employee_scope

    query = select(WorkflowTodo)
    count_query = select(func.count()).select_from(WorkflowTodo)

    def _apply(stmt):
        if scope is not None:
            stmt = apply_employee_scope(stmt, scope, WorkflowTodo.employee_id)
        if status:
            stmt = stmt.where(WorkflowTodo.status == status)
        if todo_type:
            stmt = stmt.where(WorkflowTodo.todo_type == todo_type)
        if business_type:
            stmt = stmt.where(WorkflowTodo.business_type == business_type)
        if employee_id is not None:
            stmt = stmt.where(WorkflowTodo.employee_id == employee_id)
        if assignee_role:
            stmt = stmt.where(WorkflowTodo.assignee_role == assignee_role)
        if assignee_user_id is not None:
            stmt = stmt.where(WorkflowTodo.assignee_user_id == assignee_user_id)
        if keyword:
            stmt = stmt.where(
                or_(
                    WorkflowTodo.title.ilike(f"%{keyword}%"),
                    WorkflowTodo.description.ilike(f"%{keyword}%"),
                )
            )
        return stmt

    query = _apply(query)
    count_query = _apply(count_query)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(
                (WorkflowTodo.status == "pending").desc(),
                WorkflowTodo.priority.desc(),
                WorkflowTodo.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    emps = await _employee_map(db, {r.employee_id for r in rows if r.employee_id})
    return [_todo_out(r, emps.get(r.employee_id) if r.employee_id else None) for r in rows], total


async def todos_summary(db: AsyncSession) -> dict:
    rows = (
        await db.execute(
            select(WorkflowTodo.status, WorkflowTodo.todo_type, func.count()).group_by(
                WorkflowTodo.status, WorkflowTodo.todo_type
            )
        )
    ).all()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    pending = 0
    for status, todo_type, cnt in rows:
        by_status[status] = by_status.get(status, 0) + cnt
        by_type[todo_type] = by_type.get(todo_type, 0) + cnt
        if status == "pending":
            pending += cnt
    return {
        "pending": by_status.get("pending", 0),
        "completed": by_status.get("completed", 0),
        "cancelled": by_status.get("cancelled", 0),
        "by_type": by_type,
    }


async def get_todo(db: AsyncSession, todo_id: int) -> dict:
    todo = (
        await db.execute(select(WorkflowTodo).where(WorkflowTodo.id == todo_id))
    ).scalar_one_or_none()
    if todo is None:
        raise ResourceNotFound(f"Todo {todo_id} not found")
    emp = None
    if todo.employee_id:
        emp = (
            await db.execute(select(Employee).where(Employee.id == todo.employee_id))
        ).scalar_one_or_none()
    return _todo_out(todo, emp)


async def complete_todo_by_id(
    db: AsyncSession,
    todo_id: int,
    *,
    completed_by: int | None = None,
) -> dict:
    todo = (
        await db.execute(
            select(WorkflowTodo).where(WorkflowTodo.id == todo_id).with_for_update()
        )
    ).scalar_one_or_none()
    if todo is None:
        raise ResourceNotFound(f"Todo {todo_id} not found")
    if todo.status == "completed":
        return await get_todo(db, todo_id)
    if todo.status == "cancelled":
        raise ConflictError("Todo already cancelled")
    await complete_todo(db, todo, completed_by=completed_by)
    await db.commit()
    return await get_todo(db, todo_id)


async def cancel_todo_by_id(
    db: AsyncSession,
    todo_id: int,
    *,
    reason: str | None = None,
    completed_by: int | None = None,
) -> dict:
    todo = (
        await db.execute(
            select(WorkflowTodo).where(WorkflowTodo.id == todo_id).with_for_update()
        )
    ).scalar_one_or_none()
    if todo is None:
        raise ResourceNotFound(f"Todo {todo_id} not found")
    if todo.status == "cancelled":
        return await get_todo(db, todo_id)
    if todo.status == "completed":
        raise ConflictError("Todo already completed")
    await cancel_todo(db, todo, reason=reason, completed_by=completed_by)
    await db.commit()
    return await get_todo(db, todo_id)


# ---- Alerts ----


async def upsert_alert(
    db: AsyncSession,
    *,
    alert_type: str,
    fingerprint: str,
    title: str,
    detail: str | None = None,
    severity: str = "warning",
    employee_id: int | None = None,
    bed_id: int | None = None,
    accommodation_id: int | None = None,
    business_type: str | None = None,
    business_id: int | None = None,
) -> WorkflowAlert:
    """Create an active alert, or return the existing active one (idempotent)."""
    existing = (
        await db.execute(
            select(WorkflowAlert)
            .where(
                WorkflowAlert.fingerprint == fingerprint,
                WorkflowAlert.status == "active",
            )
            .with_for_update()
        )
    ).scalars().first()
    if existing is not None:
        return existing

    alert = WorkflowAlert(
        alert_type=alert_type,
        severity=severity,
        employee_id=employee_id,
        bed_id=bed_id,
        accommodation_id=accommodation_id,
        business_type=business_type,
        business_id=business_id,
        title=title,
        detail=detail,
        status="active",
        fingerprint=fingerprint,
        detected_at=utcnow(),
    )
    db.add(alert)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(WorkflowAlert).where(
                    WorkflowAlert.fingerprint == fingerprint,
                    WorkflowAlert.status == "active",
                )
            )
        ).scalars().first()
        if existing is None:
            raise ConflictError("Duplicate workflow alert") from None
        return existing
    return alert


async def resolve_alerts(
    db: AsyncSession,
    *,
    fingerprint: str | None = None,
    alert_type: str | None = None,
    employee_id: int | None = None,
    accommodation_id: int | None = None,
    bed_id: int | None = None,
    business_type: str | None = None,
    business_id: int | None = None,
    reason: str | None = None,
    resolved_by: int | None = None,
) -> list[WorkflowAlert]:
    query = select(WorkflowAlert).where(WorkflowAlert.status == "active")
    if fingerprint is not None:
        query = query.where(WorkflowAlert.fingerprint == fingerprint)
    if alert_type is not None:
        query = query.where(WorkflowAlert.alert_type == alert_type)
    if employee_id is not None:
        query = query.where(WorkflowAlert.employee_id == employee_id)
    if accommodation_id is not None:
        query = query.where(WorkflowAlert.accommodation_id == accommodation_id)
    if bed_id is not None:
        query = query.where(WorkflowAlert.bed_id == bed_id)
    if business_type is not None:
        query = query.where(WorkflowAlert.business_type == business_type)
    if business_id is not None:
        query = query.where(WorkflowAlert.business_id == business_id)
    rows = (await db.execute(query.with_for_update())).scalars().all()
    now = utcnow()
    for alert in rows:
        alert.status = "resolved"
        alert.resolved_at = now
        alert.resolved_by = resolved_by
        alert.resolve_reason = reason
    if rows:
        await db.flush()
    return list(rows)


async def list_alerts(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = "active",
    alert_type: str | None = None,
    employee_id: int | None = None,
    keyword: str | None = None,
    scope=None,
) -> tuple[list[dict], int]:
    from app.services.data_scope import apply_employee_scope

    query = select(WorkflowAlert)
    count_query = select(func.count()).select_from(WorkflowAlert)

    def _apply(stmt):
        if scope is not None:
            stmt = apply_employee_scope(stmt, scope, WorkflowAlert.employee_id)
        if status:
            stmt = stmt.where(WorkflowAlert.status == status)
        if alert_type:
            stmt = stmt.where(WorkflowAlert.alert_type == alert_type)
        if employee_id is not None:
            stmt = stmt.where(WorkflowAlert.employee_id == employee_id)
        if keyword:
            stmt = stmt.where(
                or_(
                    WorkflowAlert.title.ilike(f"%{keyword}%"),
                    WorkflowAlert.detail.ilike(f"%{keyword}%"),
                )
            )
        return stmt

    query = _apply(query)
    count_query = _apply(count_query)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(WorkflowAlert.detected_at.desc(), WorkflowAlert.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    emps = await _employee_map(db, {r.employee_id for r in rows if r.employee_id})
    return [
        _alert_out(r, emps.get(r.employee_id) if r.employee_id else None) for r in rows
    ], total


async def alerts_summary(db: AsyncSession) -> dict:
    rows = (
        await db.execute(
            select(WorkflowAlert.status, WorkflowAlert.alert_type, func.count()).group_by(
                WorkflowAlert.status, WorkflowAlert.alert_type
            )
        )
    ).all()
    by_type: dict[str, int] = {}
    active = 0
    resolved = 0
    for status, alert_type, cnt in rows:
        if status == "active":
            active += cnt
            by_type[alert_type] = by_type.get(alert_type, 0) + cnt
        else:
            resolved += cnt
    return {"active": active, "resolved": resolved, "by_type": by_type}


async def get_alert(db: AsyncSession, alert_id: int) -> dict:
    alert = (
        await db.execute(select(WorkflowAlert).where(WorkflowAlert.id == alert_id))
    ).scalar_one_or_none()
    if alert is None:
        raise ResourceNotFound(f"Alert {alert_id} not found")
    emp = None
    if alert.employee_id:
        emp = (
            await db.execute(select(Employee).where(Employee.id == alert.employee_id))
        ).scalar_one_or_none()
    return _alert_out(alert, emp)


async def resolve_alert_by_id(
    db: AsyncSession,
    alert_id: int,
    *,
    reason: str | None = None,
    resolved_by: int | None = None,
) -> dict:
    alert = (
        await db.execute(
            select(WorkflowAlert).where(WorkflowAlert.id == alert_id).with_for_update()
        )
    ).scalar_one_or_none()
    if alert is None:
        raise ResourceNotFound(f"Alert {alert_id} not found")
    if alert.status == "resolved":
        return await get_alert(db, alert_id)
    await resolve_alerts(
        db,
        fingerprint=alert.fingerprint,
        reason=reason,
        resolved_by=resolved_by,
    )
    await db.commit()
    return await get_alert(db, alert_id)


# ---- Notifications ----


async def push_notification(
    db: AsyncSession,
    *,
    title: str,
    content: str | None = None,
    category: str = "system",
    user_id: int | None = None,
    role_code: str | None = None,
    business_type: str | None = None,
    business_id: int | None = None,
) -> Notification:
    note = Notification(
        user_id=user_id,
        role_code=role_code,
        category=category,
        title=title,
        content=content,
        business_type=business_type,
        business_id=business_id,
        created_at=utcnow(),
    )
    db.add(note)
    await db.flush()
    return note


async def list_notifications(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    user_id: int | None = None,
    role_code: str | None = None,
    unread_only: bool = False,
) -> tuple[list[dict], int]:
    query = select(Notification)
    count_query = select(func.count()).select_from(Notification)

    def _apply(stmt):
        if user_id is not None:
            stmt = stmt.where(
                or_(Notification.user_id == user_id, Notification.role_code == role_code)
            )
        elif role_code:
            stmt = stmt.where(Notification.role_code == role_code)
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        return stmt

    query = _apply(query)
    count_query = _apply(count_query)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(Notification.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
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
    return items, total
