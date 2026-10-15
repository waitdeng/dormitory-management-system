"""Check-in application lifecycle: create → approve → reserve → confirm.

State machine (spec §4.2):
  pending → approved → reserved → checked_in
  also: rejected / cancelled / expired

All mutations run in one transaction with the shared lock order
(employee → beds ascending → business rows). See occupancy.py.
"""

from __future__ import annotations

from datetime import date, datetime

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
    AccommodationApplication,
    AccommodationRecord,
    BedReservation,
)
from app.models.base import utcnow
from app.models.employee import Employee
from app.services import audit_service
from app.services import occupancy as occ
from app.services import workflow_service as wf

APPLICATION_TYPES = {"new", "recheck", "temporary"}
OPEN_STATUSES = ("pending", "approved", "reserved")


def _app_out(app: AccommodationApplication, employee: Employee | None = None) -> dict:
    data = {
        "id": app.id,
        "application_no": app.application_no,
        "employee_id": app.employee_id,
        "application_type": app.application_type,
        "requested_checkin_date": app.requested_checkin_date,
        "assigned_bed_id": app.assigned_bed_id,
        "status": app.status,
        "reason": app.reason,
        "notes": app.notes,
        "submitted_by": app.submitted_by,
        "processed_by": app.processed_by,
        "processed_at": app.processed_at,
        "created_at": app.created_at,
        "updated_at": app.updated_at,
    }
    if employee is not None:
        data["employee_no"] = employee.employee_no
        data["employee_name"] = employee.full_name
        data["department_id"] = employee.department_id
    return data


def _bed_chain_dict(chain: dict) -> dict:
    """Unified bed display: 区域 / 楼栋 / 楼层 / 房间号 / 床位号."""
    bed = chain["bed"]
    room = chain["room"]
    floor = chain["floor"]
    building = chain["building"]
    area = chain["area"]
    bed_path = "/".join(
        str(p)
        for p in (area.area_name, building.building_name, floor.floor_no, room.room_no, bed.bed_no)
        if p is not None
    )
    return {
        "id": bed.id,
        "bed_no": bed.bed_no,
        "room_no": room.room_no,
        "floor_no": floor.floor_no,
        "building_name": building.building_name,
        "area_name": area.area_name,
        "bed_path": bed_path,
    }


async def _resolve_app_bed_id(db: AsyncSession, app: AccommodationApplication) -> int | None:
    """Business display rule (HOTFIX-06):
    1) active accommodation bed (post-transfer current bed wins)
    2) active reservation bed (已预留)
    3) historical assigned/ended bed for 已入住 traceability
    4) None → UI shows 未分配 (approved without reservation)
    """
    from sqlalchemy import select as _select

    acc = (
        await db.execute(
            _select(AccommodationRecord)
            .where(
                AccommodationRecord.application_id == app.id,
                AccommodationRecord.status == "active",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if acc is not None and acc.bed_id is not None:
        return acc.bed_id

    res = (
        await db.execute(
            _select(BedReservation)
            .where(
                BedReservation.application_id == app.id,
                BedReservation.status == "active",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if res is not None:
        return res.bed_id

    # 已预留 / 已批准 without active reservation → 未分配
    # (assigned_bed_id alone is not a current assignment)
    if app.status in {"reserved", "approved"}:
        return None

    # 已入住: keep historical path (ended acc / assigned bed) for audit trail
    if app.status == "checked_in":
        ended = (
            await db.execute(
                _select(AccommodationRecord)
                .where(
                    AccommodationRecord.application_id == app.id,
                    AccommodationRecord.bed_id.is_not(None),
                )
                .order_by(AccommodationRecord.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if ended is not None:
            return ended.bed_id
        return app.assigned_bed_id

    return app.assigned_bed_id


async def _attach_bed(db: AsyncSession, data: dict, app: AccommodationApplication) -> dict:
    bed_id = await _resolve_app_bed_id(db, app)
    if bed_id is None:
        data["bed"] = None
        return data
    try:
        chain = await occ.load_bed_chain(db, bed_id)
        data["bed"] = _bed_chain_dict(chain)
    except Exception:  # noqa: BLE001 — never break list rendering
        data["bed"] = None
    return data


def _res_out(res: BedReservation) -> dict:
    return {
        "id": res.id,
        "reservation_no": res.reservation_no,
        "application_id": res.application_id,
        "employee_id": res.employee_id,
        "bed_id": res.bed_id,
        "status": res.status,
        "reserved_at": res.reserved_at,
        "expires_at": res.expires_at,
        "released_at": res.released_at,
        "release_reason": res.release_reason,
        "created_by": res.created_by,
        "created_at": res.created_at,
        "updated_at": res.updated_at,
    }


def _acc_out(rec: AccommodationRecord, employee: Employee | None = None) -> dict:
    data = {
        "id": rec.id,
        "employee_id": rec.employee_id,
        "bed_id": rec.bed_id,
        "application_id": rec.application_id,
        "checkin_at": rec.checkin_at,
        "checkout_at": rec.checkout_at,
        "status": rec.status,
        "end_reason": rec.end_reason,
        "created_by": rec.created_by,
        "ended_by": rec.ended_by,
        "notes": rec.notes,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
    }
    if employee is not None:
        data["employee_no"] = employee.employee_no
        data["employee_name"] = employee.full_name
    return data


async def _peek_app(db: AsyncSession, app_id: int) -> AccommodationApplication:
    """Load application WITHOUT lock (for lock-ordering only).

    HOTFIX-07A: never take the application row lock before employee/bed locks.
    """
    app = (
        await db.execute(
            select(AccommodationApplication).where(AccommodationApplication.id == app_id)
        )
    ).scalar_one_or_none()
    if app is None:
        raise ResourceNotFound(f"Check-in application {app_id} not found")
    return app


async def _lock_app(db: AsyncSession, app_id: int) -> AccommodationApplication:
    """Lock application AFTER employee+bed locks (AGENTS.md lock order)."""
    app = (
        await db.execute(
            select(AccommodationApplication)
            .where(AccommodationApplication.id == app_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if app is None:
        raise ResourceNotFound(f"Check-in application {app_id} not found")
    return app


async def _load_app(db: AsyncSession, app_id: int) -> AccommodationApplication:
    """Backward-compatible alias — prefer _peek_app + _lock_app in write paths."""
    return await _peek_app(db, app_id)


async def _load_emp(db: AsyncSession, employee_id: int) -> Employee:
    emp = (
        await db.execute(select(Employee).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if emp is None:
        raise ResourceNotFound(f"Employee {employee_id} not found")
    return emp


async def list_applications(
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

    query = select(AccommodationApplication)
    count_query = select(func.count()).select_from(AccommodationApplication)

    if scope is not None:
        query = apply_employee_scope(query, scope, AccommodationApplication.employee_id)
        count_query = apply_employee_scope(
            count_query, scope, AccommodationApplication.employee_id
        )
    if status:
        query = query.where(AccommodationApplication.status == status)
        count_query = count_query.where(AccommodationApplication.status == status)
    if employee_id is not None:
        query = query.where(AccommodationApplication.employee_id == employee_id)
        count_query = count_query.where(
            AccommodationApplication.employee_id == employee_id
        )
    if keyword:
        emp_ids = select(Employee.id).where(
            or_(
                Employee.employee_no.ilike(f"%{keyword}%"),
                Employee.full_name.ilike(f"%{keyword}%"),
            )
        )
        cond = or_(
            AccommodationApplication.application_no.ilike(f"%{keyword}%"),
            AccommodationApplication.employee_id.in_(emp_ids),
        )
        query = query.where(cond)
        count_query = count_query.where(cond)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(AccommodationApplication.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    emp_map: dict[int, Employee] = {}
    if rows:
        ids = {r.employee_id for r in rows}
        for e in (await db.execute(select(Employee).where(Employee.id.in_(ids)))).scalars():
            emp_map[e.id] = e
    items = []
    for r in rows:
        item = _app_out(r, emp_map.get(r.employee_id))
        item = await _attach_bed(db, item, r)
        items.append(item)
    return items, total


async def get_application(db: AsyncSession, app_id: int) -> dict:
    app = (
        await db.execute(
            select(AccommodationApplication).where(AccommodationApplication.id == app_id)
        )
    ).scalar_one_or_none()
    if app is None:
        raise ResourceNotFound(f"Check-in application {app_id} not found")
    emp = await _load_emp(db, app.employee_id)
    data = _app_out(app, emp)
    data = await _attach_bed(db, data, app)
    res = (
        await db.execute(
            select(BedReservation).where(
                BedReservation.application_id == app.id,
                BedReservation.status == "active",
            )
        )
    ).scalars().first()
    data["reservation"] = _res_out(res) if res else None
    acc = (
        await db.execute(
            select(AccommodationRecord).where(
                AccommodationRecord.application_id == app.id,
                AccommodationRecord.status == "active",
            )
        )
    ).scalars().first()
    data["accommodation"] = _acc_out(acc) if acc else None
    return data


async def create_application(
    db: AsyncSession,
    *,
    employee_id: int,
    application_type: str = "new",
    requested_checkin_date: date | None = None,
    reason: str | None = None,
    notes: str | None = None,
    idempotency_key: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    if application_type not in APPLICATION_TYPES:
        raise ValidationError(
            f"application_type must be one of {sorted(APPLICATION_TYPES)}"
        )

    if idempotency_key:
        existing = (
            await db.execute(
                select(AccommodationApplication).where(
                    AccommodationApplication.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await get_application(db, existing.id)

    emp = await occ.lock_employee(db, employee_id)
    occ.assert_eligible_for_new_checkin(emp)
    await occ.assert_employee_available_for_checkin(db, employee_id, employee=emp)

    open_app = await occ.open_application_for_employee(db, employee_id)
    if open_app is not None:
        raise ConflictError(
            f"Employee already has an open check-in application {open_app.application_no}"
        )

    app = AccommodationApplication(
        application_no=occ.biz_no("CA"),
        employee_id=employee_id,
        application_type=application_type,
        requested_checkin_date=requested_checkin_date,
        status="pending",
        reason=reason,
        notes=notes,
        submitted_by=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(app)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Duplicate check-in application") from exc

    await audit_service.write_audit(
        db,
        action="checkin.application.create",
        resource_type="accommodation_application",
        resource_id=app.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_app_out(app, emp),
    )
    await db.commit()
    return await get_application(db, app.id)


async def approve_application(
    db: AsyncSession,
    app_id: int,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    app = await _load_app(db, app_id)
    if app.status == "approved":
        return await get_application(db, app_id)  # idempotent
    if app.status != "pending":
        raise ConflictError(f"Cannot approve application in status '{app.status}'")

    emp = await occ.lock_employee(db, app.employee_id)
    app.status = "approved"
    app.processed_by = actor_user_id
    app.processed_at = utcnow()
    await audit_service.write_audit(
        db,
        action="checkin.application.approve",
        resource_type="accommodation_application",
        resource_id=app.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_app_out(app, emp),
    )
    await db.commit()
    return await get_application(db, app_id)


async def reject_application(
    db: AsyncSession,
    app_id: int,
    *,
    reason: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    app = await _load_app(db, app_id)
    if app.status == "rejected":
        return await get_application(db, app_id)
    if app.status != "pending":
        raise ConflictError(f"Cannot reject application in status '{app.status}'")

    app.status = "rejected"
    if reason:
        app.reason = reason
    app.processed_by = actor_user_id
    app.processed_at = utcnow()
    await audit_service.write_audit(
        db,
        action="checkin.application.reject",
        resource_type="accommodation_application",
        resource_id=app.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_app_out(app),
    )
    await db.commit()
    return await get_application(db, app_id)


async def reserve_bed(
    db: AsyncSession,
    app_id: int,
    *,
    bed_id: int,
    expires_at: datetime | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    peek = await _peek_app(db, app_id)
    emp = await occ.lock_employee(db, peek.employee_id)
    await occ.lock_beds(db, [bed_id])
    app = await _lock_app(db, app_id)

    if app.status == "reserved" and app.assigned_bed_id == bed_id:
        return await get_application(db, app_id)  # idempotent same-bed reserve
    if app.status not in ("approved", "pending"):
        # allow reserve from approved (normal) or pending (back-office shortcut
        # still requires explicit approve first per state machine)
        raise ConflictError(
            f"Cannot reserve bed for application in status '{app.status}'"
        )
    if app.status == "pending":
        raise ConflictError("Application must be approved before reserving a bed")

    chain = await occ.load_bed_chain(db, bed_id)
    occ.assert_hierarchy_allocatable(chain)
    occ.assert_gender_policy(chain, emp)

    # release previous reservation on this application if any
    prev = (
        await db.execute(
            select(BedReservation)
            .where(
                BedReservation.application_id == app.id,
                BedReservation.status == "active",
            )
            .with_for_update()
        )
    ).scalars().first()
    if prev is not None and prev.bed_id != bed_id:

        prev.status = "cancelled"
        prev.released_at = utcnow()
        prev.release_reason = "re-reserved to another bed"

    occ.assert_eligible_for_new_checkin(emp)
    await occ.assert_bed_free_for(db, bed_id, employee_id=emp.id)
    await occ.assert_employee_available_for_checkin(db, emp.id, employee=emp)


    res = BedReservation(
        reservation_no=occ.biz_no("BR"),
        application_id=app.id,
        employee_id=emp.id,
        bed_id=bed_id,
        status="active",
        reserved_at=utcnow(),
        expires_at=expires_at,
        created_by=actor_user_id,
    )
    db.add(res)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Bed is already reserved or occupied") from exc

    app.assigned_bed_id = bed_id
    app.status = "reserved"
    app.processed_by = actor_user_id
    app.processed_at = utcnow()

    await audit_service.write_audit(
        db,
        action="checkin.reserve",
        resource_type="bed_reservation",
        resource_id=res.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_res_out(res),
    )
    await db.commit()
    return await get_application(db, app_id)


async def confirm_checkin(
    db: AsyncSession,
    app_id: int,
    *,
    checkin_at: datetime | None = None,
    notes: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:

    peek = await _peek_app(db, app_id)
    peek_bed = peek.assigned_bed_id
    emp = await occ.lock_employee(db, peek.employee_id)
    if peek_bed:
        await occ.lock_beds(db, [peek_bed])
    app = await _lock_app(db, app_id)

    # Idempotent: already checked in — return existing state, no second record.
    if app.status == "checked_in":
        return await get_application(db, app_id)
    if app.status != "reserved":
        raise ConflictError(f"Cannot confirm check-in in status '{app.status}'")
    if not app.assigned_bed_id:
        raise BusinessRuleError("Application has no assigned bed")

    bed_id = app.assigned_bed_id
    if not peek_bed or peek_bed != bed_id:
        await occ.lock_beds(db, [bed_id])

    res = (
        await db.execute(
            select(BedReservation)
            .where(
                BedReservation.application_id == app.id,
                BedReservation.status == "active",
            )
            .with_for_update()
        )
    ).scalars().first()
    if res is None:
        # HOTFIX-07A: concurrent duplicate confirm may observe the reservation
        # already consumed by the peer transaction. Treat as idempotent success
        # when this application already produced an active accommodation.
        existing_acc = (
            await db.execute(
                select(AccommodationRecord)
                .where(
                    AccommodationRecord.application_id == app.id,
                    AccommodationRecord.status == "active",
                )
                .with_for_update()
            )
        ).scalars().first()
        if existing_acc is not None:
            app.status = "checked_in"
            return await get_application(db, app_id)
        raise ConflictError("No active reservation found for this application")

    # DMS-P1-004: a reservation past expires_at is logically invalid even if
    # the background scanner has not flipped its status yet.
    if res.expires_at is not None and res.expires_at <= utcnow():
        raise ConflictError(
            f"Reservation {res.reservation_no} expired at {res.expires_at}; "
            f"re-reserve a bed before confirming check-in"
        )

    occ.assert_eligible_for_new_checkin(emp)
    await occ.assert_bed_free_for(
        db, bed_id, employee_id=emp.id, ignore_reservation_id=res.id
    )
    await occ.assert_employee_available_for_checkin(db, emp.id, employee=emp)

    rec = AccommodationRecord(
        employee_id=emp.id,
        bed_id=bed_id,
        application_id=app.id,
        checkin_at=checkin_at or utcnow(),
        status="active",
        created_by=actor_user_id,
        notes=notes,
    )
    db.add(rec)
    res.status = "consumed"
    res.released_at = utcnow()
    res.release_reason = "consumed by check-in confirmation"
    app.status = "checked_in"
    app.processed_by = actor_user_id
    app.processed_at = utcnow()

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Confirm check-in conflicts with existing occupancy") from exc

    # M4: resolve overdue / reservation alerts for this employee & application
    await wf.resolve_alerts(
        db,
        alert_type="overdue_checkin",
        business_id=app.id,
        reason="check-in confirmed",
        resolved_by=actor_user_id,
    )
    await wf.resolve_alerts(
        db,
        alert_type="reservation_overdue",
        business_id=res.id,
        reason="check-in confirmed",
        resolved_by=actor_user_id,
    )
    await wf.complete_todos_for_business(
        db,
        business_type="reservation",
        business_id=res.id,
        completed_by=actor_user_id,
        reason="check-in confirmed",
    )
    await wf.complete_todos_for_business(
        db,
        business_type="application",
        business_id=app.id,
        completed_by=actor_user_id,
        reason="check-in confirmed",
    )

    await audit_service.write_audit(
        db,
        action="checkin.confirm",
        resource_type="accommodation_record",
        resource_id=rec.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_acc_out(rec, emp),
    )
    await db.commit()
    return await get_application(db, app_id)


async def cancel_application(
    db: AsyncSession,
    app_id: int,
    *,
    reason: str | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:

    peek = await _peek_app(db, app_id)
    emp = await occ.lock_employee(db, peek.employee_id)
    if peek.assigned_bed_id:
        await occ.lock_beds(db, [peek.assigned_bed_id])
    app = await _lock_app(db, app_id)
    if app.status == "cancelled":
        return await get_application(db, app_id)
    if app.status not in OPEN_STATUSES:
        raise ConflictError(f"Cannot cancel application in status '{app.status}'")

    # lock reservation if any, then release
    if app.assigned_bed_id and app.assigned_bed_id != peek.assigned_bed_id:
        await occ.lock_beds(db, [app.assigned_bed_id])
    res = (
        await db.execute(
            select(BedReservation)
            .where(
                BedReservation.application_id == app.id,
                BedReservation.status == "active",
            )
            .with_for_update()
        )
    ).scalars().first()
    if res is not None:
        res.status = "cancelled"
        res.released_at = utcnow()
        res.release_reason = reason or "application cancelled"

    app.status = "cancelled"
    if reason:
        app.reason = reason
    app.processed_by = actor_user_id
    app.processed_at = utcnow()

    await audit_service.write_audit(
        db,
        action="checkin.application.cancel",
        resource_type="accommodation_application",
        resource_id=app.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_app_out(app),
    )
    await db.commit()
    return await get_application(db, app_id)


async def list_active_accommodations(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    employee_id: int | None = None,
    bed_id: int | None = None,
    building_id: int | None = None,
    scope=None,
) -> tuple[list[dict], int]:
    from app.models.dorm import DormBed, DormFloor, DormRoom
    from app.services.data_scope import apply_employee_scope

    query = select(AccommodationRecord).where(AccommodationRecord.status == "active")
    count_query = (
        select(func.count())
        .select_from(AccommodationRecord)
        .where(AccommodationRecord.status == "active")
    )
    if scope is not None:
        query = apply_employee_scope(query, scope, AccommodationRecord.employee_id)
        count_query = apply_employee_scope(count_query, scope, AccommodationRecord.employee_id)
    if employee_id is not None:
        query = query.where(AccommodationRecord.employee_id == employee_id)
        count_query = count_query.where(AccommodationRecord.employee_id == employee_id)
    if bed_id is not None:
        query = query.where(AccommodationRecord.bed_id == bed_id)
        count_query = count_query.where(AccommodationRecord.bed_id == bed_id)
    if building_id is not None:
        bed_ids = (
            select(DormBed.id)
            .join(DormRoom, DormBed.room_id == DormRoom.id)
            .join(DormFloor, DormRoom.floor_id == DormFloor.id)
            .where(DormFloor.building_id == building_id)
        )
        query = query.where(AccommodationRecord.bed_id.in_(bed_ids))
        count_query = count_query.where(AccommodationRecord.bed_id.in_(bed_ids))

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(AccommodationRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items: list[dict] = []
    for rec in rows:
        emp = await _load_emp(db, rec.employee_id)
        chain = await occ.load_bed_chain(db, rec.bed_id)
        items.append(
            {
                **_acc_out(rec, emp),
                "bed_no": chain["bed"].bed_no,
                "room_no": chain["room"].room_no,
                "floor_no": chain["floor"].floor_no,
                "building_name": chain["building"].building_name,
                "area_name": chain["area"].area_name,
            }
        )
    return items, total


async def get_accommodation(db: AsyncSession, rec_id: int) -> dict:
    rec = (
        await db.execute(
            select(AccommodationRecord).where(AccommodationRecord.id == rec_id)
        )
    ).scalar_one_or_none()
    if rec is None:
        raise ResourceNotFound(f"Accommodation record {rec_id} not found")
    emp = await _load_emp(db, rec.employee_id)
    chain = await occ.load_bed_chain(db, rec.bed_id)
    return {
        **_acc_out(rec, emp),
        "bed_no": chain["bed"].bed_no,
        "room_no": chain["room"].room_no,
        "floor_no": chain["floor"].floor_no,
        "building_name": chain["building"].building_name,
        "area_name": chain["area"].area_name,
    }


async def list_history(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    employee_id: int | None = None,
    include_active: bool = False,
    scope=None,
) -> tuple[list[dict], int]:
    from app.services.data_scope import apply_employee_scope

    query = select(AccommodationRecord)
    count_query = select(func.count()).select_from(AccommodationRecord)
    if scope is not None:
        query = apply_employee_scope(query, scope, AccommodationRecord.employee_id)
        count_query = apply_employee_scope(count_query, scope, AccommodationRecord.employee_id)
    if not include_active:
        query = query.where(AccommodationRecord.status != "active")
        count_query = count_query.where(AccommodationRecord.status != "active")
    if employee_id is not None:
        query = query.where(AccommodationRecord.employee_id == employee_id)
        count_query = count_query.where(AccommodationRecord.employee_id == employee_id)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(AccommodationRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items: list[dict] = []
    for rec in rows:
        emp = await _load_emp(db, rec.employee_id)
        chain = await occ.load_bed_chain(db, rec.bed_id)
        items.append(
            {
                **_acc_out(rec, emp),
                "bed_no": chain["bed"].bed_no,
                "room_no": chain["room"].room_no,
                "floor_no": chain["floor"].floor_no,
                "building_name": chain["building"].building_name,
                "area_name": chain["area"].area_name,
            }
        )
    return items, total
