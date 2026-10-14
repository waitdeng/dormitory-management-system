"""Employee offboarding / termination workflow (M4, spec §4.5 / BR-006).

HR status events (offboarding → terminated) generate admin check-out to-dos
and “terminated still housed” alerts. They NEVER free the bed or end the
accommodation record — only an explicit check-out completion does that.

Idempotency:
  - employee_status_events UNIQUE (source, source_event_id)
  - workflow_todos UNIQUE open_business_key (pending only)
  - workflow_alerts UNIQUE active_fingerprint
Repeated offboarding / termination therefore do not duplicate side-effects.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ResourceNotFound, ValidationError
from app.models.base import utcnow
from app.models.employee import Employee
from app.models.workflow import EmployeeStatusEvent
from app.services import audit_service
from app.services import occupancy as occ
from app.services import workflow_service as wf

EVENT_OFFBOARDING = "offboarding"
EVENT_TERMINATED = "terminated"
EVENT_REACTIVATED = "reactivated"
EVENT_STATUS_CHANGE = "status_change"

ALLOWED_EMPLOYMENT_STATUS = {
    "pending",
    "active",
    "probation",
    "offboarding",
    "terminated",
    "resigned",
    "suspended",
}

# Legal forward transitions for dedicated endpoints
OFFBOARDING_TARGET = "offboarding"
TERMINATED_TARGET = "terminated"


def _event_out(event: EmployeeStatusEvent) -> dict:
    return {
        "id": event.id,
        "employee_id": event.employee_id,
        "event_type": event.event_type,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "source": event.source,
        "source_event_id": event.source_event_id,
        "reason": event.reason,
        "notes": event.notes,
        "created_by": event.created_by,
        "created_at": event.created_at,
    }


async def _load_employee(db: AsyncSession, employee_id: int) -> Employee:
    emp = (
        await db.execute(select(Employee).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if emp is None:
        raise ResourceNotFound(f"Employee {employee_id} not found")
    return emp


async def find_status_event(
    db: AsyncSession, *, source: str, source_event_id: str, for_update: bool = False
) -> EmployeeStatusEvent | None:
    stmt = select(EmployeeStatusEvent).where(
        EmployeeStatusEvent.source == source,
        EmployeeStatusEvent.source_event_id == source_event_id,
    )
    if for_update:
        # Locking read: must see rows committed by concurrent peers even under
        # REPEATABLE READ (plain SELECT would miss them).
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_status_events(
    db: AsyncSession, employee_id: int
) -> list[dict]:
    rows = (
        await db.execute(
            select(EmployeeStatusEvent)
            .where(EmployeeStatusEvent.employee_id == employee_id)
            .order_by(EmployeeStatusEvent.id.desc())
        )
    ).scalars().all()
    return [_event_out(r) for r in rows]


async def _record_event(
    db: AsyncSession,
    *,
    employee: Employee,
    event_type: str,
    from_status: str | None,
    to_status: str,
    source: str,
    source_event_id: str,
    reason: str | None,
    notes: str | None,
    created_by: int | None,
) -> EmployeeStatusEvent | None:
    """Insert status event; returns None when this source_event_id was already handled."""
    existing = await find_status_event(
        db, source=source, source_event_id=source_event_id, for_update=True
    )
    if existing is not None:
        return None

    event = EmployeeStatusEvent(
        employee_id=employee.id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        source=source,
        source_event_id=source_event_id,
        reason=reason,
        notes=notes,
        created_by=created_by,
        created_at=utcnow(),
    )
    db.add(event)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return None
    return event


async def _ensure_offboarding_checkout_side_effects(
    db: AsyncSession,
    *,
    employee: Employee,
    actor_user_id: int | None,
    source_event_id: str,
) -> dict:
    """Ensure open checkout + admin to-do when the employee is still housed.

    Never ends the accommodation or frees the bed (BR-006).
    """
    acc = await occ.active_accommodation_for_employee(db, employee.id, for_update=True)
    checkout_id = None
    todo_id = None
    if acc is None:
        return {
            "accommodation_id": None,
            "checkout_id": None,
            "todo_id": None,
            "bed_id": None,
        }

    # Lock the occupied bed so concurrent allocation / checkout stay consistent
    await occ.lock_beds(db, [acc.bed_id])

    open_co = await occ.open_checkout_for_accommodation(db, acc.id)
    if open_co is None:
        from app.models.accommodation import CheckoutRecord

        co = CheckoutRecord(
            checkout_no=occ.biz_no("CO"),
            employee_id=employee.id,
            accommodation_id=acc.id,
            checkout_type="offboarding",
            reason="离职退宿",
            status="pending",
            processed_by=actor_user_id,
        )
        db.add(co)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError(
                "Duplicate checkout for this accommodation"
            ) from exc
        open_co = co
    checkout_id = open_co.id

    chain = await occ.load_bed_chain(db, acc.bed_id)
    location = (
        f"{chain['building'].building_name} {chain['room'].room_no} "
        f"{chain['bed'].bed_no}"
    )
    todo = await wf.ensure_todo(
        db,
        todo_type="checkout_offboarding",
        business_type="checkout",
        business_id=open_co.id,
        employee_id=employee.id,
        title=f"离职退宿：{employee.full_name}（{employee.employee_no}）",
        description=(
            f"员工已进入离职流程，请完成宿舍检查并办理退宿。\n"
            f"床位：{location}\n住宿记录：{acc.id}"
        ),
        assignee_role=wf.DEFAULT_DORM_ROLE,
        priority="high",
        source_event_id=source_event_id,
        created_by=actor_user_id,
    )
    todo_id = todo.id

    await wf.push_notification(
        db,
        title=f"待办：离职退宿 {employee.full_name}",
        content=f"请办理退宿并释放床位 {location}",
        category="todo",
        role_code=wf.DEFAULT_DORM_ROLE,
        business_type="checkout",
        business_id=open_co.id,
    )
    return {
        "accommodation_id": acc.id,
        "checkout_id": checkout_id,
        "todo_id": todo_id,
        "bed_id": acc.bed_id,
    }


async def _ensure_terminated_still_housed_alert(
    db: AsyncSession,
    *,
    employee: Employee,
    accommodation_id: int,
    bed_id: int,
    actor_user_id: int | None,
) -> int | None:
    chain = await occ.load_bed_chain(db, bed_id)
    location = (
        f"{chain['building'].building_name} {chain['room'].room_no} {chain['bed'].bed_no}"
    )
    alert = await wf.upsert_alert(
        db,
        alert_type="terminated_still_housed",
        fingerprint=f"terminated_still_housed:{employee.id}:{accommodation_id}",
        title=f"离职未退宿：{employee.full_name}（{employee.employee_no}）",
        detail=(
            f"员工人事状态为 terminated，但仍占用床位 {location}。"
            f"住宿记录 {accommodation_id} 仍为 active，请尽快办理退宿。"
        ),
        severity="critical",
        employee_id=employee.id,
        bed_id=bed_id,
        accommodation_id=accommodation_id,
        business_type="employee",
        business_id=employee.id,
    )
    await wf.push_notification(
        db,
        title=f"预警：离职未退宿 {employee.full_name}",
        content=f"床位 {location} 仍被离职员工占用",
        category="alert",
        role_code=wf.DEFAULT_DORM_ROLE,
        business_type="employee",
        business_id=employee.id,
    )
    _ = actor_user_id  # reserved for future audit linkage on alert create
    return alert.id


async def start_offboarding(
    db: AsyncSession,
    employee_id: int,
    *,
    reason: str | None = None,
    notes: str | None = None,
    termination_date=None,
    idempotency_key: str | None = None,
    source: str = "api",
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """HR starts offboarding (employment_status → offboarding).

    Side-effects when still housed: open checkout + admin to-do. Bed stays
    occupied and the active accommodation record is untouched.
    """
    emp = await occ.lock_employee(db, employee_id)
    # Scope custom keys per employee so two employees never share one event id.
    source_event_id = (
        f"emp{employee_id}:{idempotency_key}"
        if idempotency_key
        else f"offboarding:{employee_id}"
    )

    # Already handled this exact event → return current state (idempotent).
    prior = await find_status_event(
        db, source=source, source_event_id=source_event_id, for_update=True
    )
    if prior is not None:
        if prior.employee_id != employee_id:
            raise ConflictError("idempotency_key already used for another employee")
        # Side-effects are ensure_*-style and idempotent: a retry after a
        # partial failure must still leave exactly one open checkout/to-do.
        side = await _ensure_offboarding_checkout_side_effects(
            db,
            employee=emp,
            actor_user_id=actor_user_id,
            source_event_id=source_event_id,
        )
        await db.commit()
        result = await _offboarding_result(db, emp, prior, created=False, side=side)
        return result

    # Already in / past offboarding without this event id: still create the
    # event once per source_event_id, but do not change status backwards and
    # do not duplicate side-effects (ensure_* is idempotent).
    from_status = emp.employment_status
    if from_status not in ALLOWED_EMPLOYMENT_STATUS:
        raise ValidationError(f"Unknown employment_status '{from_status}'")

    # terminated employees should not silently go back to offboarding
    if from_status == "terminated":
        raise ConflictError(
            "Employee is already terminated; use terminate with a new event id "
            "or reactivate first"
        )

    if from_status != OFFBOARDING_TARGET:
        emp.employment_status = OFFBOARDING_TARGET
    if termination_date is not None:
        emp.termination_date = termination_date

    event = await _record_event(
        db,
        employee=emp,
        event_type=EVENT_OFFBOARDING,
        from_status=from_status,
        to_status=OFFBOARDING_TARGET,
        source=source,
        source_event_id=source_event_id,
        reason=reason,
        notes=notes,
        created_by=actor_user_id,
    )
    if event is None:
        # Lost a race on the unique (source, source_event_id) — treat as done.
        await db.rollback()
        prior = await find_status_event(
            db, source=source, source_event_id=source_event_id, for_update=True
        )
        if prior is None:
            raise ConflictError("Status event conflict")
        emp = await occ.lock_employee(db, employee_id)
        side = await _ensure_offboarding_checkout_side_effects(
            db,
            employee=emp,
            actor_user_id=actor_user_id,
            source_event_id=source_event_id,
        )
        await db.commit()
        return await _offboarding_result(db, emp, prior, created=False, side=side)

    side = await _ensure_offboarding_checkout_side_effects(
        db,
        employee=emp,
        actor_user_id=actor_user_id,
        source_event_id=source_event_id,
    )

    await audit_service.write_audit(
        db,
        action="employee.offboarding",
        resource_type="employee",
        resource_id=emp.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data={"employment_status": from_status},
        after_data={
            "employment_status": emp.employment_status,
            "event_id": event.id,
            **side,
        },
        detail=reason,
    )
    await db.commit()
    return await _offboarding_result(db, emp, event, created=True, side=side)


async def terminate_employee(
    db: AsyncSession,
    employee_id: int,
    *,
    reason: str | None = None,
    notes: str | None = None,
    termination_date=None,
    idempotency_key: str | None = None,
    source: str = "api",
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """HR confirms termination (employment_status → terminated).

    If the employee is still housed, raise a “离职未退宿” alert and keep the
    bed occupied. Does NOT auto-release the bed (BR-006 / P0 B).
    """
    emp = await occ.lock_employee(db, employee_id)
    source_event_id = (
        f"emp{employee_id}:{idempotency_key}"
        if idempotency_key
        else f"terminate:{employee_id}"
    )

    prior = await find_status_event(
        db, source=source, source_event_id=source_event_id, for_update=True
    )
    if prior is not None:
        if prior.employee_id != employee_id:
            raise ConflictError("idempotency_key already used for another employee")
        side = await _ensure_offboarding_checkout_side_effects(
            db,
            employee=emp,
            actor_user_id=actor_user_id,
            source_event_id=source_event_id,
        )
        alert_id = None
        if side["accommodation_id"] is not None and emp.employment_status == "terminated":
            alert_id = await _ensure_terminated_still_housed_alert(
                db,
                employee=emp,
                accommodation_id=side["accommodation_id"],
                bed_id=side["bed_id"],
                actor_user_id=actor_user_id,
            )
        await db.commit()
        result = await _offboarding_result(db, emp, prior, created=False, side=side)
        result["alert_id"] = alert_id
        return result

    from_status = emp.employment_status
    if from_status not in ALLOWED_EMPLOYMENT_STATUS:
        raise ValidationError(f"Unknown employment_status '{from_status}'")

    if from_status != TERMINATED_TARGET:
        emp.employment_status = TERMINATED_TARGET
    if termination_date is not None:
        emp.termination_date = termination_date
    elif emp.termination_date is None:
        emp.termination_date = utcnow().date()

    event = await _record_event(
        db,
        employee=emp,
        event_type=EVENT_TERMINATED,
        from_status=from_status,
        to_status=TERMINATED_TARGET,
        source=source,
        source_event_id=source_event_id,
        reason=reason,
        notes=notes,
        created_by=actor_user_id,
    )
    if event is None:
        await db.rollback()
        prior = await find_status_event(
            db, source=source, source_event_id=source_event_id, for_update=True
        )
        if prior is None:
            raise ConflictError("Status event conflict")
        emp = await occ.lock_employee(db, employee_id)
        side = await _ensure_offboarding_checkout_side_effects(
            db,
            employee=emp,
            actor_user_id=actor_user_id,
            source_event_id=source_event_id,
        )
        alert_id = None
        if side["accommodation_id"] is not None and emp.employment_status == "terminated":
            alert_id = await _ensure_terminated_still_housed_alert(
                db,
                employee=emp,
                accommodation_id=side["accommodation_id"],
                bed_id=side["bed_id"],
                actor_user_id=actor_user_id,
            )
        await db.commit()
        result = await _offboarding_result(db, emp, prior, created=False, side=side)
        result["alert_id"] = alert_id
        return result

    side = await _ensure_offboarding_checkout_side_effects(
        db,
        employee=emp,
        actor_user_id=actor_user_id,
        source_event_id=source_event_id,
    )
    alert_id = None
    if side["accommodation_id"] is not None:
        alert_id = await _ensure_terminated_still_housed_alert(
            db,
            employee=emp,
            accommodation_id=side["accommodation_id"],
            bed_id=side["bed_id"],
            actor_user_id=actor_user_id,
        )

    await audit_service.write_audit(
        db,
        action="employee.terminate",
        resource_type="employee",
        resource_id=emp.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data={"employment_status": from_status},
        after_data={
            "employment_status": emp.employment_status,
            "event_id": event.id,
            "alert_id": alert_id,
            **side,
        },
        detail=reason,
    )
    await db.commit()
    result = await _offboarding_result(db, emp, event, created=True, side=side)
    result["alert_id"] = alert_id
    return result


async def apply_status_change(
    db: AsyncSession,
    employee_id: int,
    *,
    new_status: str,
    reason: str | None = None,
    notes: str | None = None,
    termination_date=None,
    idempotency_key: str | None = None,
    source: str = "api",
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """Route employment_status changes through the event pipeline.

    Used by PATCH /employees/{id} so that setting offboarding/terminated via
    the generic update API produces the same todos/alerts as the dedicated
    endpoints (P0 A/B).
    """
    if new_status not in ALLOWED_EMPLOYMENT_STATUS:
        raise ValidationError(
            f"employment_status must be one of {sorted(ALLOWED_EMPLOYMENT_STATUS)}"
        )

    if new_status == OFFBOARDING_TARGET:
        return await start_offboarding(
            db,
            employee_id,
            reason=reason,
            notes=notes,
            termination_date=termination_date,
            idempotency_key=idempotency_key,
            source=source,
            actor_user_id=actor_user_id,
            request_id=request_id,
        )
    if new_status == TERMINATED_TARGET:
        return await terminate_employee(
            db,
            employee_id,
            reason=reason,
            notes=notes,
            termination_date=termination_date,
            idempotency_key=idempotency_key,
            source=source,
            actor_user_id=actor_user_id,
            request_id=request_id,
        )

    # Other statuses: record a generic status_change event without workflow side-effects
    emp = await occ.lock_employee(db, employee_id)
    from_status = emp.employment_status
    source_event_id = (
        f"emp{employee_id}:{idempotency_key}"
        if idempotency_key
        else f"status:{employee_id}:{from_status}->{new_status}"
    )
    prior = await find_status_event(
        db, source=source, source_event_id=source_event_id, for_update=True
    )
    if prior is not None:
        await db.commit()
        return await _offboarding_result(db, emp, prior, created=False)

    emp.employment_status = new_status
    if termination_date is not None:
        emp.termination_date = termination_date

    event_type = (
        EVENT_REACTIVATED
        if new_status in ("active", "probation")
        else EVENT_STATUS_CHANGE
    )
    event = await _record_event(
        db,
        employee=emp,
        event_type=event_type,
        from_status=from_status,
        to_status=new_status,
        source=source,
        source_event_id=source_event_id,
        reason=reason,
        notes=notes,
        created_by=actor_user_id,
    )
    if event is None:
        await db.rollback()
        prior = await find_status_event(
            db, source=source, source_event_id=source_event_id, for_update=True
        )
        if prior is None:
            raise ConflictError("Status event conflict")
        emp = await occ.lock_employee(db, employee_id)
        return await _offboarding_result(db, emp, prior, created=False)

    await audit_service.write_audit(
        db,
        action="employee.status_change",
        resource_type="employee",
        resource_id=emp.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data={"employment_status": from_status},
        after_data={"employment_status": emp.employment_status, "event_id": event.id},
        detail=reason,
    )
    await db.commit()
    return await _offboarding_result(db, emp, event, created=True)


async def _offboarding_result(
    db: AsyncSession,
    emp: Employee,
    event: EmployeeStatusEvent | None,
    *,
    created: bool,
    side: dict | None = None,
) -> dict:
    acc = await occ.active_accommodation_for_employee(db, emp.id)
    return {
        "employee_id": emp.id,
        "employee_no": emp.employee_no,
        "full_name": emp.full_name,
        "employment_status": emp.employment_status,
        "termination_date": emp.termination_date,
        "event": _event_out(event) if event is not None else None,
        "event_created": created,
        "accommodation": (
            {
                "id": acc.id,
                "bed_id": acc.bed_id,
                "status": acc.status,
            }
            if acc is not None
            else None
        ),
        "side_effects": side or {},
    }


async def pending_offboarding_checkouts(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """Open check-outs for employees in offboarding / terminated status."""
    from sqlalchemy import func

    from app.models.accommodation import CheckoutRecord

    base = (
        select(CheckoutRecord)
        .join(Employee, Employee.id == CheckoutRecord.employee_id)
        .where(
            CheckoutRecord.status.in_(("pending", "inspection")),
            CheckoutRecord.checkout_type == "offboarding",
            Employee.employment_status.in_(("offboarding", "terminated")),
        )
    )
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(CheckoutRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    emps = await wf._employee_map(db, {r.employee_id for r in rows})
    items = []
    for r in rows:
        emp = emps.get(r.employee_id)
        items.append(
            {
                "id": r.id,
                "checkout_no": r.checkout_no,
                "employee_id": r.employee_id,
                "employee_no": emp.employee_no if emp else None,
                "employee_name": emp.full_name if emp else None,
                "employment_status": emp.employment_status if emp else None,
                "accommodation_id": r.accommodation_id,
                "status": r.status,
                "expected_checkout_date": r.expected_checkout_date,
                "created_at": r.created_at,
            }
        )
    return items, total
