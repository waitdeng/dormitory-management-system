"""Check-out workflow (退宿).

State machine (spec §4.2): pending → inspection → completed; cancelled before complete.

Complete ends the accommodation record and frees the bed. At most one open
checkout per accommodation (DB generated-column unique). Lock order:
employee → bed → accommodation/checkout rows.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    ResourceNotFound,
    ValidationError,
)
from app.models.accommodation import AccommodationRecord, CheckoutRecord
from app.models.base import utcnow
from app.models.employee import Employee
from app.services import audit_service
from app.services import occupancy as occ
from app.services import workflow_service as wf

CHECKOUT_TYPES = {"normal", "offboarding", "other"}


def _co_out(co: CheckoutRecord, employee: Employee | None = None) -> dict:
    data = {
        "id": co.id,
        "checkout_no": co.checkout_no,
        "employee_id": co.employee_id,
        "accommodation_id": co.accommodation_id,
        "checkout_type": co.checkout_type,
        "reason": co.reason,
        "status": co.status,
        "expected_checkout_date": co.expected_checkout_date,
        "actual_checkout_at": co.actual_checkout_at,
        "key_returned": co.key_returned,
        "access_card_returned": co.access_card_returned,
        "belongings_cleared": co.belongings_cleared,
        "room_inspected": co.room_inspected,
        "inspection_notes": co.inspection_notes,
        "processed_by": co.processed_by,
        "completed_at": co.completed_at,
        "created_at": co.created_at,
        "updated_at": co.updated_at,
    }
    if employee is not None:
        data["employee_no"] = employee.employee_no
        data["employee_name"] = employee.full_name
    return data


async def _load_co(db: AsyncSession, checkout_id: int) -> CheckoutRecord:
    co = (
        await db.execute(
            select(CheckoutRecord)
            .where(CheckoutRecord.id == checkout_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if co is None:
        raise ResourceNotFound(f"Checkout {checkout_id} not found")
    return co


async def list_checkouts(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    employee_id: int | None = None,
    keyword: str | None = None,
    scope=None,
) -> tuple[list[dict], int]:
    from app.services.data_scope import apply_employee_scope

    query = select(CheckoutRecord)
    count_query = select(func.count()).select_from(CheckoutRecord)

    if scope is not None:
        query = apply_employee_scope(query, scope, CheckoutRecord.employee_id)
        count_query = apply_employee_scope(count_query, scope, CheckoutRecord.employee_id)
    if status:
        query = query.where(CheckoutRecord.status == status)
        count_query = count_query.where(CheckoutRecord.status == status)
    if employee_id is not None:
        query = query.where(CheckoutRecord.employee_id == employee_id)
        count_query = count_query.where(CheckoutRecord.employee_id == employee_id)
    if keyword:
        emp_ids = select(Employee.id).where(
            or_(
                Employee.employee_no.ilike(f"%{keyword}%"),
                Employee.full_name.ilike(f"%{keyword}%"),
            )
        )
        cond = or_(
            CheckoutRecord.checkout_no.ilike(f"%{keyword}%"),
            CheckoutRecord.employee_id.in_(emp_ids),
        )
        query = query.where(cond)
        count_query = count_query.where(cond)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(CheckoutRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    emp_map: dict[int, Employee] = {}
    if rows:
        ids = {r.employee_id for r in rows}
        for e in (await db.execute(select(Employee).where(Employee.id.in_(ids)))).scalars():
            emp_map[e.id] = e
    return [_co_out(r, emp_map.get(r.employee_id)) for r in rows], total


async def get_checkout(db: AsyncSession, checkout_id: int) -> dict:
    co = (
        await db.execute(select(CheckoutRecord).where(CheckoutRecord.id == checkout_id))
    ).scalar_one_or_none()
    if co is None:
        raise ResourceNotFound(f"Checkout {checkout_id} not found")
    emp = (
        await db.execute(select(Employee).where(Employee.id == co.employee_id))
    ).scalar_one()
    data = _co_out(co, emp)
    rec = (
        await db.execute(
            select(AccommodationRecord).where(
                AccommodationRecord.id == co.accommodation_id
            )
        )
    ).scalar_one_or_none()
    if rec is not None:
        chain = await occ.load_bed_chain(db, rec.bed_id)
        data["accommodation"] = {
            "id": rec.id,
            "bed_id": rec.bed_id,
            "status": rec.status,
            "checkin_at": rec.checkin_at,
            "checkout_at": rec.checkout_at,
            "bed_no": chain["bed"].bed_no,
            "room_no": chain["room"].room_no,
            "building_name": chain["building"].building_name,
        }
    return data


async def create_checkout(
    db: AsyncSession,
    *,
    employee_id: int,
    checkout_type: str = "normal",
    reason: str | None = None,
    expected_checkout_date: date | None = None,
    notes: str | None = None,
    idempotency_key: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    if checkout_type not in CHECKOUT_TYPES:
        raise ValidationError(f"checkout_type must be one of {sorted(CHECKOUT_TYPES)}")

    if idempotency_key:
        existing = (
            await db.execute(
                select(CheckoutRecord).where(
                    CheckoutRecord.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await get_checkout(db, existing.id)

    emp = await occ.lock_employee(db, employee_id)
    acc = await occ.active_accommodation_for_employee(db, employee_id, for_update=True)
    if acc is None:
        raise BusinessRuleError("Employee has no active accommodation to check out")

    open_co = await occ.open_checkout_for_accommodation(db, acc.id)
    if open_co is not None:
        raise ConflictError(
            f"Accommodation already has an open checkout {open_co.checkout_no}"
        )

    await occ.lock_beds(db, [acc.bed_id])

    co = CheckoutRecord(
        checkout_no=occ.biz_no("CO"),
        employee_id=employee_id,
        accommodation_id=acc.id,
        checkout_type=checkout_type,
        reason=reason,
        status="pending",
        expected_checkout_date=expected_checkout_date,
        inspection_notes=notes,
        idempotency_key=idempotency_key,
        processed_by=actor_user_id,
    )
    db.add(co)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Duplicate checkout for this accommodation") from exc

    await audit_service.write_audit(
        db,
        action="checkout.create",
        resource_type="checkout_record",
        resource_id=co.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_co_out(co, emp),
    )
    await db.commit()
    return await get_checkout(db, co.id)


async def record_inspection(
    db: AsyncSession,
    checkout_id: int,
    *,
    key_returned: bool | None = None,
    access_card_returned: bool | None = None,
    belongings_cleared: bool | None = None,
    room_inspected: bool | None = None,
    inspection_notes: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    co = await _load_co(db, checkout_id)
    if co.status in ("completed", "cancelled"):
        raise ConflictError(f"Cannot inspect checkout in status '{co.status}'")

    if key_returned is not None:
        co.key_returned = key_returned
    if access_card_returned is not None:
        co.access_card_returned = access_card_returned
    if belongings_cleared is not None:
        co.belongings_cleared = belongings_cleared
    if room_inspected is not None:
        co.room_inspected = room_inspected
    if inspection_notes is not None:
        co.inspection_notes = inspection_notes

    if co.status == "pending":
        co.status = "inspection"
    co.processed_by = actor_user_id

    await audit_service.write_audit(
        db,
        action="checkout.inspect",
        resource_type="checkout_record",
        resource_id=co.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_co_out(co),
    )
    await db.commit()
    return await get_checkout(db, checkout_id)


async def complete_checkout(
    db: AsyncSession,
    checkout_id: int,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    co = await _load_co(db, checkout_id)
    if co.status == "completed":
        return await get_checkout(db, checkout_id)  # idempotent
    if co.status == "cancelled":
        raise ConflictError("Checkout already cancelled")
    if co.status not in ("pending", "inspection"):
        raise ConflictError(f"Cannot complete checkout in status '{co.status}'")

    emp = await occ.lock_employee(db, co.employee_id)
    acc = (
        await db.execute(
            select(AccommodationRecord)
            .where(AccommodationRecord.id == co.accommodation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if acc is None:
        raise ResourceNotFound("Accommodation record not found")
    if acc.status != "active":
        if acc.status == "ended":
            # Source record already ended (transfer or prior checkout).
            # If the employee moved to a new bed, this checkout is stale.
            current = await occ.active_accommodation_for_employee(db, emp.id)
            if current is not None and current.id != acc.id:
                raise ConflictError(
                    "Accommodation was superseded by a transfer; cancel this checkout"
                )
            co.status = "completed"
            co.completed_at = co.completed_at or utcnow()
            co.actual_checkout_at = co.actual_checkout_at or acc.checkout_at
            co.processed_by = actor_user_id
            await db.commit()
            return await get_checkout(db, checkout_id)
        raise ConflictError(f"Accommodation status is '{acc.status}', cannot end")

    # Refuse checkout-complete while a transfer is still open on this employee.
    open_tr = await occ.open_transfer_for_employee(db, emp.id)
    if open_tr is not None:
        raise ConflictError(
            f"Employee has an open transfer {open_tr.transfer_no}; finish or cancel it first"
        )

    await occ.lock_beds(db, [acc.bed_id])

    now = utcnow()
    acc.status = "ended"
    acc.checkout_at = now
    acc.end_reason = co.checkout_type or "checkout"
    acc.ended_by = actor_user_id

    co.status = "completed"
    co.completed_at = now
    co.actual_checkout_at = now
    co.processed_by = actor_user_id

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Checkout conflicts with accommodation state") from exc

    # M4: auto-close related to-dos and alerts once the business is done
    closed_todos = await wf.complete_todos_for_business(
        db,
        business_type="checkout",
        business_id=co.id,
        completed_by=actor_user_id,
        reason="checkout completed",
    )
    closed_todos += await wf.complete_todos_for_employee(
        db,
        employee_id=co.employee_id,
        todo_types=("checkout_offboarding",),
        completed_by=actor_user_id,
        reason="checkout completed",
    )
    resolved_alerts = await wf.resolve_alerts(
        db,
        alert_type="terminated_still_housed",
        employee_id=co.employee_id,
        accommodation_id=acc.id,
        reason="checkout completed",
        resolved_by=actor_user_id,
    )
    await wf.resolve_alerts(
        db,
        alert_type="overdue_checkout",
        business_id=co.id,
        reason="checkout completed",
        resolved_by=actor_user_id,
    )
    await wf.push_notification(
        db,
        title=f"退宿完成：{emp.full_name}",
        content=f"住宿记录 {acc.id} 已结束，床位 {acc.bed_id} 已释放",
        category="checkout",
        role_code="dorm_admin",
        business_type="checkout",
        business_id=co.id,
    )

    await audit_service.write_audit(
        db,
        action="checkout.complete",
        resource_type="checkout_record",
        resource_id=co.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={
            "checkout": _co_out(co, emp),
            "accommodation_id": acc.id,
            "bed_id": acc.bed_id,
            "closed_todos": [t.id for t in closed_todos],
            "resolved_alerts": [a.id for a in resolved_alerts],
        },
    )
    await db.commit()
    return await get_checkout(db, checkout_id)


async def cancel_checkout(
    db: AsyncSession,
    checkout_id: int,
    *,
    reason: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    co = await _load_co(db, checkout_id)
    if co.status == "cancelled":
        return await get_checkout(db, checkout_id)
    if co.status == "completed":
        raise ConflictError("Completed checkout cannot be cancelled")

    co.status = "cancelled"
    if reason:
        co.reason = reason
    co.processed_by = actor_user_id

    await audit_service.write_audit(
        db,
        action="checkout.cancel",
        resource_type="checkout_record",
        resource_id=co.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_co_out(co),
    )
    await db.commit()
    return await get_checkout(db, checkout_id)
