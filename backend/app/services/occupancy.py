"""Shared occupancy helpers: lock order, conflict checks, derived bed status.

Lock order (AGENTS.md §4 / spec §5.4):
  1. employee row (FOR UPDATE)
  2. bed rows by bed_id ascending (FOR UPDATE)
  3. accommodation / reservation / business document rows

Cross-table occupancy vs reservation conflicts MUST be re-checked here after
locks are held — generated-column unique indexes only cover one table.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ConflictError
from app.models.accommodation import (
    AccommodationApplication,
    AccommodationRecord,
    BedReservation,
    CheckoutRecord,
    TransferRecord,
)
from app.models.dorm import DormArea, DormBed, DormBuilding, DormFloor, DormRoom
from app.models.employee import Employee


def biz_no(prefix: str) -> str:
    """Business document number, unique enough with DB UNIQUE constraints."""
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:4].upper()}"


async def lock_employee(db: AsyncSession, employee_id: int) -> Employee:
    emp = (
        await db.execute(
            select(Employee).where(Employee.id == employee_id).with_for_update()
        )
    ).scalar_one_or_none()
    if emp is None:
        raise BusinessRuleError(f"Employee {employee_id} not found")
    return emp


async def lock_beds(db: AsyncSession, bed_ids: list[int]) -> dict[int, DormBed]:
    """Lock beds in ascending id order. Returns id -> bed map."""
    ids = sorted({int(b) for b in bed_ids})
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(DormBed)
            .where(DormBed.id.in_(ids))
            .order_by(DormBed.id)
            .with_for_update()
        )
    ).scalars().all()
    found = {b.id: b for b in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        raise BusinessRuleError(f"Beds not found: {missing}")
    return found


async def load_bed_chain(db: AsyncSession, bed_id: int) -> dict:
    """Load bed + room + floor + building + area without locking (for display)."""
    row = (
        await db.execute(
            select(DormBed, DormRoom, DormFloor, DormBuilding, DormArea)
            .join(DormRoom, DormBed.room_id == DormRoom.id)
            .join(DormFloor, DormRoom.floor_id == DormFloor.id)
            .join(DormBuilding, DormFloor.building_id == DormBuilding.id)
            .join(DormArea, DormBuilding.area_id == DormArea.id)
            .where(DormBed.id == bed_id)
        )
    ).first()
    if row is None:
        raise BusinessRuleError(f"Bed {bed_id} not found")
    bed, room, floor, building, area = row
    return {
        "bed": bed,
        "room": room,
        "floor": floor,
        "building": building,
        "area": area,
    }


def assert_hierarchy_allocatable(chain: dict) -> None:
    """Reject allocation when any ancestor or the bed is not operational (BR-009)."""
    for label, node in (
        ("area", chain["area"]),
        ("building", chain["building"]),
        ("floor", chain["floor"]),
        ("room", chain["room"]),
    ):
        if node.status != "active":
            raise ConflictError(f"Cannot allocate: {label} is {node.status}")
    bed = chain["bed"]
    if bed.operational_status != "active":
        raise ConflictError(
            f"Cannot allocate: bed operational_status is {bed.operational_status}"
        )


def assert_gender_policy(chain: dict, employee: Employee) -> None:
    room_policy = chain["room"].gender_policy
    if room_policy in (None, "any"):
        return
    gender = (employee.gender or "").lower()
    # accept male/female/other; only enforce when both sides are specific
    if gender and room_policy in ("male", "female") and gender != room_policy:
        raise ConflictError(
            f"Gender policy mismatch: room requires {room_policy}, employee is {gender}"
        )


async def active_accommodation_for_employee(
    db: AsyncSession, employee_id: int, *, for_update: bool = False
) -> AccommodationRecord | None:
    stmt: Select = select(AccommodationRecord).where(
        AccommodationRecord.employee_id == employee_id,
        AccommodationRecord.status == "active",
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def active_accommodation_for_bed(
    db: AsyncSession, bed_id: int, *, for_update: bool = False
) -> AccommodationRecord | None:
    stmt = select(AccommodationRecord).where(
        AccommodationRecord.bed_id == bed_id,
        AccommodationRecord.status == "active",
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def active_reservation_for_employee(
    db: AsyncSession, employee_id: int, *, for_update: bool = False
) -> BedReservation | None:
    stmt = select(BedReservation).where(
        BedReservation.employee_id == employee_id,
        BedReservation.status == "active",
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def active_reservation_for_bed(
    db: AsyncSession, bed_id: int, *, for_update: bool = False
) -> BedReservation | None:
    stmt = select(BedReservation).where(
        BedReservation.bed_id == bed_id,
        BedReservation.status == "active",
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def assert_bed_free_for(
    db: AsyncSession,
    bed_id: int,
    *,
    employee_id: int,
    ignore_reservation_id: int | None = None,
    ignore_accommodation_id: int | None = None,
) -> None:
    """Cross-table free check: no other occupancy and no other reservation."""
    occ = await active_accommodation_for_bed(db, bed_id, for_update=True)
    if occ is not None and occ.id != ignore_accommodation_id:
        raise ConflictError(f"Bed {bed_id} already has an active occupancy")

    res = await active_reservation_for_bed(db, bed_id, for_update=True)
    if res is not None and res.id != ignore_reservation_id:
        # own reservation (same employee) may be consumed, not ignored blindly
        if res.employee_id != employee_id:
            raise ConflictError(f"Bed {bed_id} is already reserved by another employee")
        if ignore_reservation_id is None and res.application_id is not None:
            # same employee holding a reservation for another application
            raise ConflictError(f"Bed {bed_id} is already reserved for this employee")


def assert_accommodation_required(emp: Employee) -> None:
    """BUG-007/BUG-014: eligibility for new bed allocation.

    Central guard for check-in application, bed reservation, confirmation,
    transfer allocation and batch import. Frontend filtering is not sufficient.
    """
    if not emp.accommodation_required:
        raise BusinessRuleError(
            f"Employee {emp.employee_no} does not require accommodation "
            f"and cannot be assigned a bed"
        )


def assert_eligible_for_new_checkin(emp: Employee) -> None:
    """BUG-014: visual-allocation / new check-in eligibility.

    Only employment_status=active may receive a NEW bed assignment.
    Transfer of already-housed employees is intentionally not restricted here.
    """
    assert_accommodation_required(emp)
    if emp.employment_status != "active":
        raise BusinessRuleError(
            f"Employee {emp.employee_no} employment_status="
            f"'{emp.employment_status}' is not eligible for new bed allocation "
            f"(only active)"
        )


async def assert_employee_available_for_checkin(
    db: AsyncSession,
    employee_id: int,
    *,
    ignore_accommodation_id: int | None = None,
    employee: Employee | None = None,
) -> None:
    """Employee must not already be actively housed (BR-003) and must need housing."""
    emp = employee
    if emp is None:
        emp = (
            await db.execute(select(Employee).where(Employee.id == employee_id))
        ).scalar_one_or_none()
        if emp is None:
            raise BusinessRuleError(f"Employee {employee_id} not found")
    assert_accommodation_required(emp)
    occ = await active_accommodation_for_employee(db, employee_id, for_update=True)
    if occ is not None and occ.id != ignore_accommodation_id:
        raise ConflictError("Employee already has an active accommodation record")


async def derive_bed_flags(
    db: AsyncSession, bed_ids: list[int]
) -> dict[int, dict[str, bool]]:
    """Compute occupied / reserved / available for a set of beds in 2 queries."""
    ids = sorted({int(b) for b in bed_ids})
    if not ids:
        return {}
    occ_rows = (
        await db.execute(
            select(AccommodationRecord.bed_id).where(
                AccommodationRecord.bed_id.in_(ids),
                AccommodationRecord.status == "active",
            )
        )
    ).scalars().all()
    res_rows = (
        await db.execute(
            select(BedReservation.bed_id).where(
                BedReservation.bed_id.in_(ids),
                BedReservation.status == "active",
            )
        )
    ).scalars().all()
    occupied = set(occ_rows)
    reserved = set(res_rows)
    return {
        bed_id: {
            "occupied": bed_id in occupied,
            "reserved": bed_id in reserved,
        }
        for bed_id in ids
    }


async def bed_status_map_for_rooms(
    db: AsyncSession, room_ids: list[int]
) -> dict[int, list[dict]]:
    """Return room_id -> [{bed_id, occupied, reserved}] for occupancy displays."""
    if not room_ids:
        return {}
    beds = (
        await db.execute(select(DormBed).where(DormBed.room_id.in_(room_ids)))
    ).scalars().all()
    flags = await derive_bed_flags(db, [b.id for b in beds])
    out: dict[int, list[dict]] = {}
    for b in beds:
        f = flags.get(b.id, {"occupied": False, "reserved": False})
        out.setdefault(b.room_id, []).append(
            {
                "bed_id": b.id,
                "bed_no": b.bed_no,
                "operational_status": b.operational_status,
                "occupied": f["occupied"],
                "reserved": f["reserved"],
            }
        )
    return out


async def count_bed_usage(db: AsyncSession, bed_ids: list[int]) -> dict[str, int]:
    ids = sorted({int(b) for b in bed_ids})
    if not ids:
        return {"occupied": 0, "reserved": 0, "free": 0}
    occupied = (
        await db.execute(
            select(func.count(func.distinct(AccommodationRecord.bed_id))).where(
                AccommodationRecord.bed_id.in_(ids),
                AccommodationRecord.status == "active",
            )
        )
    ).scalar_one()
    reserved = (
        await db.execute(
            select(func.count(func.distinct(BedReservation.bed_id))).where(
                BedReservation.bed_id.in_(ids),
                BedReservation.status == "active",
            )
        )
    ).scalar_one()
    # A bed counted in both still occupies capacity; free = neither.
    both = (
        await db.execute(
            select(func.count()).select_from(
                select(AccommodationRecord.bed_id)
                .where(
                    AccommodationRecord.bed_id.in_(ids),
                    AccommodationRecord.status == "active",
                )
                .intersect(
                    select(BedReservation.bed_id).where(
                        BedReservation.bed_id.in_(ids),
                        BedReservation.status == "active",
                    )
                )
                .subquery()
            )
        )
    ).scalar_one()
    used = occupied + reserved - (both or 0)
    return {
        "occupied": occupied,
        "reserved": reserved,
        "free": max(0, len(ids) - used),
    }


async def open_checkout_for_accommodation(
    db: AsyncSession, accommodation_id: int
) -> CheckoutRecord | None:
    return (
        await db.execute(
            select(CheckoutRecord).where(
                CheckoutRecord.accommodation_id == accommodation_id,
                CheckoutRecord.status.in_(("pending", "inspection")),
            )
        )
    ).scalar_one_or_none()


async def open_transfer_for_employee(
    db: AsyncSession, employee_id: int
) -> TransferRecord | None:
    return (
        await db.execute(
            select(TransferRecord).where(
                TransferRecord.employee_id == employee_id,
                TransferRecord.status.in_(("pending", "reserved")),
            )
        )
    ).scalar_one_or_none()


async def open_application_for_employee(
    db: AsyncSession, employee_id: int
) -> AccommodationApplication | None:
    return (
        await db.execute(
            select(AccommodationApplication).where(
                AccommodationApplication.employee_id == employee_id,
                AccommodationApplication.status.in_(
                    ("pending", "approved", "reserved")
                ),
            )
        )
    ).scalars().first()
