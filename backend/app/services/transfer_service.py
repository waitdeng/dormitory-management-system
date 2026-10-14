"""In-service bed transfer (调宿).

State machine (spec §4.2): pending → reserved → completed; cancelled before complete.

Complete is one transaction: end source accommodation, create target
accommodation, consume reservation (BR-007). Lock order: employee → beds
(source + target ascending) → business rows.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    ResourceNotFound,
    ValidationError,
)
from app.models.accommodation import (
    AccommodationRecord,
    BedReservation,
    TransferRecord,
)
from app.models.base import utcnow
from app.models.employee import Employee
from app.services import audit_service
from app.services import occupancy as occ
from app.services import workflow_service as wf


def _tr_out(tr: TransferRecord, employee: Employee | None = None) -> dict:
    data = {
        "id": tr.id,
        "transfer_no": tr.transfer_no,
        "employee_id": tr.employee_id,
        "source_accommodation_id": tr.source_accommodation_id,
        "source_bed_id": tr.source_bed_id,
        "target_bed_id": tr.target_bed_id,
        "target_reservation_id": tr.target_reservation_id,
        "target_accommodation_id": tr.target_accommodation_id,
        "reason": tr.reason,
        "status": tr.status,
        "requested_at": tr.requested_at,
        "completed_at": tr.completed_at,
        "cancelled_at": tr.cancelled_at,
        "processed_by": tr.processed_by,
        "notes": tr.notes,
        "created_at": tr.created_at,
        "updated_at": tr.updated_at,
    }
    if employee is not None:
        data["employee_no"] = employee.employee_no
        data["employee_name"] = employee.full_name
    return data


async def _load_tr(db: AsyncSession, transfer_id: int) -> TransferRecord:
    tr = (
        await db.execute(
            select(TransferRecord)
            .where(TransferRecord.id == transfer_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if tr is None:
        raise ResourceNotFound(f"Transfer {transfer_id} not found")
    return tr


async def list_transfers(
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

    query = select(TransferRecord)
    count_query = select(func.count()).select_from(TransferRecord)

    if scope is not None:
        query = apply_employee_scope(query, scope, TransferRecord.employee_id)
        count_query = apply_employee_scope(count_query, scope, TransferRecord.employee_id)
    if status:
        query = query.where(TransferRecord.status == status)
        count_query = count_query.where(TransferRecord.status == status)
    if employee_id is not None:
        query = query.where(TransferRecord.employee_id == employee_id)
        count_query = count_query.where(TransferRecord.employee_id == employee_id)
    if keyword:
        emp_ids = select(Employee.id).where(
            or_(
                Employee.employee_no.ilike(f"%{keyword}%"),
                Employee.full_name.ilike(f"%{keyword}%"),
            )
        )
        cond = or_(
            TransferRecord.transfer_no.ilike(f"%{keyword}%"),
            TransferRecord.employee_id.in_(emp_ids),
        )
        query = query.where(cond)
        count_query = count_query.where(cond)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(TransferRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    emp_map: dict[int, Employee] = {}
    if rows:
        ids = {r.employee_id for r in rows}
        for e in (await db.execute(select(Employee).where(Employee.id.in_(ids)))).scalars():
            emp_map[e.id] = e
    return [_tr_out(r, emp_map.get(r.employee_id)) for r in rows], total


async def get_transfer(db: AsyncSession, transfer_id: int) -> dict:
    tr = (
        await db.execute(select(TransferRecord).where(TransferRecord.id == transfer_id))
    ).scalar_one_or_none()
    if tr is None:
        raise ResourceNotFound(f"Transfer {transfer_id} not found")
    emp = (
        await db.execute(select(Employee).where(Employee.id == tr.employee_id))
    ).scalar_one()
    data = _tr_out(tr, emp)
    try:
        src = await occ.load_bed_chain(db, tr.source_bed_id)
        data["source_bed"] = {
            "id": src["bed"].id,
            "bed_no": src["bed"].bed_no,
            "room_no": src["room"].room_no,
            "building_name": src["building"].building_name,
        }
        tgt = await occ.load_bed_chain(db, tr.target_bed_id)
        data["target_bed"] = {
            "id": tgt["bed"].id,
            "bed_no": tgt["bed"].bed_no,
            "room_no": tgt["room"].room_no,
            "building_name": tgt["building"].building_name,
        }
    except BusinessRuleError:
        pass
    return data


async def create_transfer(
    db: AsyncSession,
    *,
    employee_id: int,
    target_bed_id: int,
    reason: str | None = None,
    notes: str | None = None,
    idempotency_key: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    if idempotency_key:
        existing = (
            await db.execute(
                select(TransferRecord).where(
                    TransferRecord.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await get_transfer(db, existing.id)

    emp = await occ.lock_employee(db, employee_id)
    src = await occ.active_accommodation_for_employee(db, employee_id, for_update=True)
    if src is None:
        raise BusinessRuleError("Employee has no active accommodation to transfer from")
    if src.bed_id == target_bed_id:
        raise ValidationError("Transfer target bed must differ from the source bed")

    open_tr = await occ.open_transfer_for_employee(db, employee_id)
    if open_tr is not None:
        raise ConflictError(
            f"Employee already has an open transfer {open_tr.transfer_no}"
        )

    # lock source + target beds (ascending)
    await occ.lock_beds(db, [src.bed_id, target_bed_id])
    chain = await occ.load_bed_chain(db, target_bed_id)
    occ.assert_hierarchy_allocatable(chain)
    occ.assert_gender_policy(chain, emp)

    tr = TransferRecord(
        transfer_no=occ.biz_no("TR"),
        employee_id=employee_id,
        source_accommodation_id=src.id,
        source_bed_id=src.bed_id,
        target_bed_id=target_bed_id,
        reason=reason,
        status="pending",
        requested_at=utcnow(),
        processed_by=actor_user_id,
        notes=notes,
        idempotency_key=idempotency_key,
    )
    db.add(tr)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Duplicate transfer") from exc

    await audit_service.write_audit(
        db,
        action="transfer.create",
        resource_type="transfer_record",
        resource_id=tr.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_tr_out(tr, emp),
    )
    await db.commit()
    return await get_transfer(db, tr.id)


async def reserve_target(
    db: AsyncSession,
    transfer_id: int,
    *,
    target_bed_id: int | None = None,
    expires_at: datetime | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    tr = await _load_tr(db, transfer_id)
    if tr.status == "completed":
        raise ConflictError("Transfer already completed")
    if tr.status == "cancelled":
        raise ConflictError("Transfer already cancelled")
    if tr.status == "reserved" and (
        target_bed_id is None or target_bed_id == tr.target_bed_id
    ):
        return await get_transfer(db, transfer_id)  # idempotent

    bed_id = target_bed_id if target_bed_id is not None else tr.target_bed_id
    if bed_id == tr.source_bed_id:
        raise ValidationError("Transfer target bed must differ from the source bed")

    emp = await occ.lock_employee(db, tr.employee_id)
    await occ.lock_beds(db, [tr.source_bed_id, bed_id])
    chain = await occ.load_bed_chain(db, bed_id)
    occ.assert_hierarchy_allocatable(chain)
    occ.assert_gender_policy(chain, emp)

    # release previous transfer reservation
    if tr.target_reservation_id:
        prev = (
            await db.execute(
                select(BedReservation)
                .where(BedReservation.id == tr.target_reservation_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if prev is not None and prev.status == "active" and prev.bed_id != bed_id:
            prev.status = "cancelled"
            prev.released_at = utcnow()
            prev.release_reason = "re-reserved transfer target"

    await occ.assert_bed_free_for(
        db,
        bed_id,
        employee_id=emp.id,
        ignore_reservation_id=tr.target_reservation_id,
    )

    res = BedReservation(
        reservation_no=occ.biz_no("BR"),
        application_id=None,
        employee_id=emp.id,
        bed_id=bed_id,
        status="active",
        reserved_at=utcnow(),
        expires_at=expires_at,
        created_by=actor_user_id,
    )
    db.add(res)
    tr.target_bed_id = bed_id
    tr.status = "reserved"
    tr.processed_by = actor_user_id
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Target bed is already reserved or occupied") from exc

    tr.target_reservation_id = res.id
    await audit_service.write_audit(
        db,
        action="transfer.reserve",
        resource_type="bed_reservation",
        resource_id=res.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={
            "transfer_id": tr.id,
            "reservation_no": res.reservation_no,
            "bed_id": bed_id,
        },
    )
    await db.commit()
    return await get_transfer(db, transfer_id)


async def complete_transfer(
    db: AsyncSession,
    transfer_id: int,
    *,
    notes: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    tr = await _load_tr(db, transfer_id)
    if tr.status == "completed":
        return await get_transfer(db, transfer_id)  # idempotent
    if tr.status == "cancelled":
        raise ConflictError("Transfer already cancelled")
    if tr.status != "reserved":
        raise ConflictError(
            f"Cannot complete transfer in status '{tr.status}' (reserve target first)"
        )

    emp = await occ.lock_employee(db, tr.employee_id)
    await occ.lock_beds(db, [tr.source_bed_id, tr.target_bed_id])

    src = (
        await db.execute(
            select(AccommodationRecord)
            .where(AccommodationRecord.id == tr.source_accommodation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if src is None or src.status != "active":
        raise ConflictError("Source accommodation is no longer active")

    open_co = await occ.open_checkout_for_accommodation(db, src.id)
    if open_co is not None:
        raise ConflictError(
            f"Accommodation has an open checkout {open_co.checkout_no}; finish or cancel it first"
        )

    res = (
        await db.execute(
            select(BedReservation)
            .where(BedReservation.id == tr.target_reservation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if res is None or res.status != "active":
        raise ConflictError("Target reservation is no longer active")

    # DMS-P1-004: reject consumption of a reservation past expires_at even if
    # the expiry scanner has not run yet.
    if res.expires_at is not None and res.expires_at <= utcnow():
        raise ConflictError(
            f"Target reservation {res.reservation_no} expired at {res.expires_at}; "
            f"re-reserve a target bed before completing the transfer"
        )

    await occ.assert_bed_free_for(
        db,
        tr.target_bed_id,
        employee_id=emp.id,
        ignore_reservation_id=res.id,
    )
    # source bed will free when src ends; target must not be the source
    if tr.target_bed_id == tr.source_bed_id:
        raise ValidationError("Transfer target bed must differ from the source bed")

    now = utcnow()
    src.status = "ended"
    src.checkout_at = now
    src.end_reason = "transfer"
    src.ended_by = actor_user_id

    new_rec = AccommodationRecord(
        employee_id=emp.id,
        bed_id=tr.target_bed_id,
        application_id=src.application_id,
        checkin_at=now,
        status="active",
        created_by=actor_user_id,
        notes=notes or f"transfer from record {src.id}",
    )
    db.add(new_rec)
    res.status = "consumed"
    res.released_at = now
    res.release_reason = "consumed by transfer completion"
    tr.status = "completed"
    tr.completed_at = now
    tr.processed_by = actor_user_id
    if notes:
        tr.notes = notes

    try:
        await db.flush()
        tr.target_accommodation_id = new_rec.id
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Transfer conflicts with existing occupancy") from exc

    await wf.resolve_alerts(
        db,
        alert_type="terminated_still_housed",
        employee_id=emp.id,
        accommodation_id=src.id,
        reason="transfer completed",
        resolved_by=actor_user_id,
    )
    await wf.complete_todos_for_business(
        db,
        business_type="transfer",
        business_id=tr.id,
        completed_by=actor_user_id,
        reason="transfer completed",
    )

    await audit_service.write_audit(
        db,
        action="transfer.complete",
        resource_type="transfer_record",
        resource_id=tr.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={
            "transfer": _tr_out(tr, emp),
            "source_accommodation_id": src.id,
            "target_accommodation_id": new_rec.id,
        },
    )
    await db.commit()
    return await get_transfer(db, transfer_id)


async def cancel_transfer(
    db: AsyncSession,
    transfer_id: int,
    *,
    reason: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    tr = await _load_tr(db, transfer_id)
    if tr.status == "cancelled":
        return await get_transfer(db, transfer_id)
    if tr.status == "completed":
        raise ConflictError("Completed transfer cannot be cancelled")

    await occ.lock_beds(db, [tr.source_bed_id, tr.target_bed_id])
    if tr.target_reservation_id:
        res = (
            await db.execute(
                select(BedReservation)
                .where(BedReservation.id == tr.target_reservation_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if res is not None and res.status == "active":
            res.status = "cancelled"
            res.released_at = utcnow()
            res.release_reason = reason or "transfer cancelled"

    tr.status = "cancelled"
    tr.cancelled_at = utcnow()
    tr.processed_by = actor_user_id
    if reason:
        tr.reason = reason

    await audit_service.write_audit(
        db,
        action="transfer.cancel",
        resource_type="transfer_record",
        resource_id=tr.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_tr_out(tr),
    )
    await db.commit()
    return await get_transfer(db, transfer_id)
