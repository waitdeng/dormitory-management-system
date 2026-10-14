"""Dashboard summary metrics (M5). Derived from authoritative business records."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.models.base import utcnow

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accommodation import (
    AccommodationRecord,
    BedReservation,
)
from app.models.department import Department
from app.models.dorm import DormBed, DormBuilding, DormFloor, DormRoom
from app.models.employee import Employee
from app.models.workflow import WorkflowAlert, WorkflowTodo
from app.services.data_scope import DeptScope, apply_employee_scope


async def dashboard_summary(db: AsyncSession, *, scope: DeptScope) -> dict:
    """Core KPIs. Vacant beds exclude reserved and non-operational beds.

    Facility capacity metrics (bed/room/building totals, vacant, occupancy rate)
    are global dorm inventory — they do not expose employee or department data.
    Employee-linked metrics (housed, today check-in/out, terminated-still-housed,
    alerts, todos, department_housed, trends) are filtered by department scope.
    """
    room_total = (
        await db.execute(
            select(func.count()).select_from(DormRoom).where(DormRoom.status == "active")
        )
    ).scalar_one()
    building_total = (
        await db.execute(
            select(func.count())
            .select_from(DormBuilding)
            .where(DormBuilding.status == "active")
        )
    ).scalar_one()

    bed_total = (
        await db.execute(
            select(func.count()).select_from(DormBed).where(DormBed.operational_status == "active")
        )
    ).scalar_one()
    bed_maintenance = (
        await db.execute(
            select(func.count())
            .select_from(DormBed)
            .where(DormBed.operational_status == "maintenance")
        )
    ).scalar_one()
    bed_disabled = (
        await db.execute(
            select(func.count())
            .select_from(DormBed)
            .where(DormBed.operational_status == "disabled")
        )
    ).scalar_one()

    occupied_q = select(func.count(func.distinct(AccommodationRecord.bed_id))).where(
        AccommodationRecord.status == "active"
    )
    reserved_q = select(func.count(func.distinct(BedReservation.bed_id))).where(
        BedReservation.status == "active"
    )
    occupied_beds = (await db.execute(occupied_q)).scalar_one()
    reserved_beds = (await db.execute(reserved_q)).scalar_one()
    # A bed occupied and reserved counts once against capacity.
    both = (
        await db.execute(
            select(func.count())
            .select_from(
                select(AccommodationRecord.bed_id)
                .where(AccommodationRecord.status == "active")
                .intersect(
                    select(BedReservation.bed_id).where(BedReservation.status == "active")
                )
                .subquery()
            )
        )
    ).scalar_one()
    used = occupied_beds + reserved_beds - (both or 0)
    vacant_beds = max(0, bed_total - used)

    housed_employees = (
        await db.execute(
            select(func.count(func.distinct(AccommodationRecord.employee_id))).where(
                AccommodationRecord.status == "active"
            )
        )
    ).scalar_one()
    if not scope.is_full:
        scoped_housed = (
            await db.execute(
                select(func.count(func.distinct(AccommodationRecord.employee_id)))
                .select_from(AccommodationRecord)
                .join(Employee, Employee.id == AccommodationRecord.employee_id)
                .where(
                    AccommodationRecord.status == "active",
                    Employee.department_id.in_(scope.department_ids or frozenset())
                    if scope.department_ids
                    else False,
                )
            )
        ).scalar_one()
        housed_employees = scoped_housed

    occupancy_rate = (
        round((occupied_beds / bed_total) * 100, 2) if bed_total else 0.0
    )

    today = utcnow().date()
    day_start = datetime.combine(today, time.min)
    day_end = datetime.combine(today, time.max)

    def _scoped(stmt, employee_col):
        """Restrict employee-linked metrics to the principal's department scope."""
        return apply_employee_scope(stmt, scope, employee_col)

    today_checkin_q = _scoped(
        select(func.count()).select_from(AccommodationRecord).where(
            AccommodationRecord.checkin_at >= day_start,
            AccommodationRecord.checkin_at <= day_end,
        ),
        AccommodationRecord.employee_id,
    )
    today_checkout_q = _scoped(
        select(func.count()).select_from(AccommodationRecord).where(
            AccommodationRecord.checkout_at >= day_start,
            AccommodationRecord.checkout_at <= day_end,
        ),
        AccommodationRecord.employee_id,
    )
    today_checkin = (await db.execute(today_checkin_q)).scalar_one()
    today_checkout = (await db.execute(today_checkout_q)).scalar_one()

    terminated_still_housed_q = _scoped(
        select(func.count())
        .select_from(AccommodationRecord)
        .join(Employee, Employee.id == AccommodationRecord.employee_id)
        .where(
            AccommodationRecord.status == "active",
            Employee.employment_status.in_(("terminated", "resigned")),
        ),
        AccommodationRecord.employee_id,
    )
    terminated_still_housed = (await db.execute(terminated_still_housed_q)).scalar_one()

    active_alerts_q = _scoped(
        select(func.count()).select_from(WorkflowAlert).where(WorkflowAlert.status == "active"),
        WorkflowAlert.employee_id,
    )
    pending_todos_q = _scoped(
        select(func.count()).select_from(WorkflowTodo).where(WorkflowTodo.status == "pending"),
        WorkflowTodo.employee_id,
    )
    active_alerts = (await db.execute(active_alerts_q)).scalar_one()
    pending_todos = (await db.execute(pending_todos_q)).scalar_one()

    dept_rows = (
        await db.execute(
            select(Department.id, Department.department_name).order_by(
                Department.department_code
            )
        )
    ).all()
    housed_by_dept_rows = (
        await db.execute(
            select(
                Employee.department_id,
                func.count(func.distinct(AccommodationRecord.employee_id)),
            )
            .select_from(AccommodationRecord)
            .join(Employee, Employee.id == AccommodationRecord.employee_id)
            .where(AccommodationRecord.status == "active", Employee.department_id.is_not(None))
            .group_by(Employee.department_id)
        )
    ).all()
    housed_map = {r[0]: r[1] for r in housed_by_dept_rows}
    if not scope.is_full:
        allowed = scope.department_ids or frozenset()
        dept_rows = [r for r in dept_rows if r[0] in allowed]
        housed_map = {k: v for k, v in housed_map.items() if k in allowed}
    # Prefer departments with current residents; cap after scope filter.
    dept_rows = sorted(
        dept_rows, key=lambda r: (-housed_map.get(r[0], 0), r[0] or 0)
    )[:50]

    return {
        "building_total": building_total,
        "room_total": room_total,
        "bed_total": bed_total,
        "bed_maintenance": bed_maintenance,
        "bed_disabled": bed_disabled,
        "occupied_beds": occupied_beds,
        "reserved_beds": reserved_beds,
        "vacant_beds": vacant_beds,
        "housed_employees": housed_employees,
        "occupancy_rate": occupancy_rate,
        "today_checkin": today_checkin,
        "today_checkout": today_checkout,
        "terminated_still_housed": terminated_still_housed,
        "active_alerts": active_alerts,
        "pending_todos": pending_todos,
        "department_housed": [
            {
                "department_id": r[0],
                "department_name": r[1],
                "housed_count": housed_map.get(r[0], 0),
            }
            for r in dept_rows
        ],
    }


async def dashboard_occupancy(db: AsyncSession, *, scope: DeptScope) -> dict:
    """Occupancy rate by building (current snapshot)."""
    buildings = (
        await db.execute(select(DormBuilding).where(DormBuilding.status == "active"))
    ).scalars().all()
    items = []
    for b in buildings:
        bed_ids = (
            select(DormBed.id)
            .select_from(
                DormBed.__table__.join(DormRoom, DormBed.room_id == DormRoom.id)
                .join(DormFloor, DormRoom.floor_id == DormFloor.id)
            )
            .where(DormFloor.building_id == b.id, DormBed.operational_status == "active")
        )
        total = (
            await db.execute(select(func.count()).select_from(bed_ids.subquery()))
        ).scalar_one()
        occupied = (
            await db.execute(
                select(func.count(func.distinct(AccommodationRecord.bed_id))).where(
                    AccommodationRecord.status == "active",
                    AccommodationRecord.bed_id.in_(bed_ids),
                )
            )
        ).scalar_one()
        items.append(
            {
                "building_id": b.id,
                "building_name": b.building_name,
                "bed_total": total,
                "occupied": occupied,
                "occupancy_rate": round((occupied / total) * 100, 2) if total else 0.0,
            }
        )
    return {"items": items}


async def dashboard_trends(
    db: AsyncSession, *, scope: DeptScope, days: int = 14
) -> dict:
    """Daily check-in / check-out counts over the last N days (UTC calendar)."""
    today = utcnow().date()
    start = today - timedelta(days=max(1, min(days, 90)) - 1)
    start_dt = datetime.combine(start, time.min)

    recs = (
        await db.execute(
            apply_employee_scope(
                select(AccommodationRecord.checkin_at, AccommodationRecord.checkout_at).where(
                    (AccommodationRecord.checkin_at >= start_dt)
                    | (AccommodationRecord.checkout_at >= start_dt)
                ),
                scope,
                AccommodationRecord.employee_id,
            )
        )
    ).all()

    buckets: dict[str, dict[str, int]] = {}
    for i in range((today - start).days + 1):
        key = (start + timedelta(days=i)).isoformat()
        buckets[key] = {"date": key, "checkin": 0, "checkout": 0}

    for checkin_at, checkout_at in recs:
        if checkin_at is not None and checkin_at.date() >= start:
            key = checkin_at.date().isoformat()
            if key in buckets:
                buckets[key]["checkin"] += 1
        if checkout_at is not None and checkout_at.date() >= start:
            key = checkout_at.date().isoformat()
            if key in buckets:
                buckets[key]["checkout"] += 1

    return {"items": [buckets[k] for k in sorted(buckets)]}
