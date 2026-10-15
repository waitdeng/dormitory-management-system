"""Background scanners: reservation expiry + abnormal alerts (M4).

Scans are idempotent — re-running them must not create duplicate expirations
or duplicate active alerts. Safe to retry after partial failure because each
reservation is re-checked under row locks before it is expired.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accommodation import (
    AccommodationApplication,
    AccommodationRecord,
    BedReservation,
    CheckoutRecord,
)
from app.models.base import utcnow
from app.models.dorm import DormBed
from app.models.employee import Employee
from app.services import audit_service
from app.services import occupancy as occ
from app.services import workflow_service as wf


async def expire_reservations(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """Release active reservations past their expires_at.

    Only status='active' rows with expires_at < now are expired. Consumed /
    cancelled / already-expired rows are never touched (专项测试 1/2/3).
    """
    ts = now or utcnow()
    candidates = (
        await db.execute(
            select(BedReservation.id).where(
                BedReservation.status == "active",
                BedReservation.expires_at.isnot(None),
                BedReservation.expires_at < ts,
            )
        )
    ).scalars().all()

    expired: list[int] = []
    skipped: list[int] = []
    for res_id in candidates:
        result = await _expire_one_reservation(
            db,
            res_id,
            now=ts,
            actor_user_id=actor_user_id,
            request_id=request_id,
        )
        if result == "expired":
            expired.append(res_id)
        else:
            skipped.append(res_id)
    return {"scanned": len(candidates), "expired": expired, "skipped": skipped}


async def _sync_app_after_reservation_expiry(
    db: AsyncSession,
    *,
    res: BedReservation,
    actor_user_id: int | None,
    request_id: str | None,
) -> bool:
    """HOTFIX-07A: reserved → approved when the reservation ends as expired.

    Preconditions (caller holds employee + bed + reservation locks):
      * application.status == 'reserved'
      * application.assigned_bed_id == res.bed_id
      * no active accommodation for this application
      * employee has no active accommodation
    """
    if res.application_id is None:
        return False
    app = (
        await db.execute(
            select(AccommodationApplication)
            .where(AccommodationApplication.id == res.application_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if app is None or app.status != "reserved":
        return False
    if app.assigned_bed_id != res.bed_id:
        return False
    app_acc = (
        await db.execute(
            select(AccommodationRecord).where(
                AccommodationRecord.application_id == app.id,
                AccommodationRecord.status == "active",
            )
        )
    ).scalars().first()
    if app_acc is not None:
        return False
    emp_acc = (
        await db.execute(
            select(AccommodationRecord).where(
                AccommodationRecord.employee_id == app.employee_id,
                AccommodationRecord.status == "active",
            )
        )
    ).scalars().first()
    if emp_acc is not None:
        return False
    before_status = app.status
    app.status = "approved"
    await audit_service.write_audit(
        db,
        action="application.reservation_expired_revert",
        resource_type="accommodation_application",
        resource_id=app.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data={"status": before_status, "assigned_bed_id": app.assigned_bed_id},
        after_data={"status": app.status, "assigned_bed_id": app.assigned_bed_id},
    )
    return True


async def _expire_one_reservation(
    db: AsyncSession,
    reservation_id: int,
    *,
    now: datetime,
    actor_user_id: int | None,
    request_id: str | None,
) -> str:
    """Expire a single reservation under locks. Returns 'expired' | 'skipped'.

    Lock order matches AGENTS.md §4 / occupancy.py:
      employee FOR UPDATE → bed(s) id-ascending FOR UPDATE → reservation /
      accommodation business rows.
    """
    # Peek without locks only to learn employee/bed ids for lock ordering.
    peek = (
        await db.execute(
            select(BedReservation).where(BedReservation.id == reservation_id)
        )
    ).scalar_one_or_none()
    if peek is None:
        return "skipped"
    if peek.status != "active":
        return "skipped"
    if peek.expires_at is None or peek.expires_at >= now:
        return "skipped"

    employee_id = peek.employee_id
    bed_id = peek.bed_id

    # 1) employee row  2) bed row  3) reservation + occupancy rows
    await occ.lock_employee(db, employee_id)
    await occ.lock_beds(db, [bed_id])

    res = (
        await db.execute(
            select(BedReservation)
            .where(BedReservation.id == reservation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if res is None:
        return "skipped"
    if res.status != "active":
        return "skipped"
    if res.expires_at is None or res.expires_at >= now:
        return "skipped"

    # An occupied bed means the reservation was consumed conceptually —
    # never free a bed that has an active occupancy (专项测试 2).
    acc = await occ.active_accommodation_for_bed(db, res.bed_id, for_update=True)
    if acc is not None and acc.employee_id == res.employee_id:
        # Reservation was fulfilled; mark consumed rather than expired.
        res.status = "consumed"
        res.released_at = now
        res.release_reason = "auto-consumed: employee already checked in"
        await db.commit()
        return "skipped"

    # Double-check no new occupancy appeared (bed already locked above)
    acc2 = await occ.active_accommodation_for_bed(db, res.bed_id, for_update=True)
    if acc2 is not None:
        res.status = "expired"
        res.released_at = now
        res.release_reason = "expired (bed occupied by another record)"
        await _sync_app_after_reservation_expiry(
            db, res=res, actor_user_id=actor_user_id, request_id=request_id
        )
        await db.commit()
        return "skipped"

    res.status = "expired"
    res.released_at = now
    res.release_reason = res.release_reason or "expired automatically"

    # HOTFIX-07A: sync application in the SAME transaction as reservation expiry.
    await _sync_app_after_reservation_expiry(
        db, res=res, actor_user_id=actor_user_id, request_id=request_id
    )

    # Close any pending to-do bound to this reservation
    await wf.complete_todos_for_business(
        db,
        business_type="reservation",
        business_id=res.id,
        completed_by=actor_user_id,
        reason="reservation expired",
    )
    await wf.resolve_alerts(
        db,
        fingerprint=f"reservation_overdue:{res.id}",
        reason="reservation expired",
        resolved_by=actor_user_id,
    )

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return "skipped"

    await audit_service.write_audit(
        db,
        action="reservation.expire",
        resource_type="bed_reservation",
        resource_id=res.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={
            "reservation_id": res.id,
            "bed_id": res.bed_id,
            "employee_id": res.employee_id,
            "status": res.status,
            "released_at": res.released_at,
            "release_reason": res.release_reason,
        },
    )
    await db.commit()
    return "expired"


async def scan_alerts(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """Detect abnormal conditions and upsert alerts (idempotent by fingerprint)."""
    ts = now or utcnow()
    created: list[int] = []

    created += await _scan_terminated_still_housed(db, now=ts)
    created += await _scan_overdue_checkins(db, now=ts)
    created += await _scan_overdue_checkouts(db, now=ts)
    created += await _scan_disabled_bed_occupied(db)
    created += await _scan_reservation_overdue(db, now=ts)

    await audit_service.write_audit(
        db,
        action="alert.scan",
        resource_type="workflow_alert",
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={"created_or_existing": created},
    )
    await db.commit()
    return {"alerts": created, "count": len(created)}


async def _scan_terminated_still_housed(db: AsyncSession, *, now: datetime) -> list[int]:
    rows = (
        await db.execute(
            select(AccommodationRecord, Employee)
            .join(Employee, Employee.id == AccommodationRecord.employee_id)
            .where(
                AccommodationRecord.status == "active",
                Employee.employment_status.in_(("terminated", "offboarding")),
            )
        )
    ).all()
    ids: list[int] = []
    for acc, emp in rows:
        # offboarding is expected to still be housed — only terminated is an alert
        if emp.employment_status != "terminated":
            continue
        alert = await wf.upsert_alert(
            db,
            alert_type="terminated_still_housed",
            fingerprint=f"terminated_still_housed:{emp.id}:{acc.id}",
            title=f"离职未退宿：{emp.full_name}（{emp.employee_no}）",
            detail=f"员工已离职但仍占用床位（住宿记录 {acc.id}，床位 {acc.bed_id}）",
            severity="critical",
            employee_id=emp.id,
            bed_id=acc.bed_id,
            accommodation_id=acc.id,
            business_type="employee",
            business_id=emp.id,
        )
        ids.append(alert.id)
    return ids


async def _scan_overdue_checkins(db: AsyncSession, *, now: datetime) -> list[int]:
    """Reserved applications whose requested_checkin_date is overdue."""
    rows = (
        await db.execute(
            select(AccommodationApplication, Employee)
            .join(Employee, Employee.id == AccommodationApplication.employee_id)
            .where(
                AccommodationApplication.status == "reserved",
                AccommodationApplication.requested_checkin_date.isnot(None),
                AccommodationApplication.requested_checkin_date < now.date(),
            )
        )
    ).all()
    ids: list[int] = []
    for app, emp in rows:
        alert = await wf.upsert_alert(
            db,
            alert_type="overdue_checkin",
            fingerprint=f"overdue_checkin:{app.id}",
            title=f"超期未入住：{emp.full_name}（{emp.employee_no}）",
            detail=(
                f"入住申请 {app.application_no} 已预留床位但超过计划入住日 "
                f"{app.requested_checkin_date}"
            ),
            severity="warning",
            employee_id=emp.id,
            bed_id=app.assigned_bed_id,
            business_type="application",
            business_id=app.id,
        )
        ids.append(alert.id)
    return ids


async def _scan_overdue_checkouts(db: AsyncSession, *, now: datetime) -> list[int]:
    rows = (
        await db.execute(
            select(CheckoutRecord, Employee)
            .join(Employee, Employee.id == CheckoutRecord.employee_id)
            .where(
                CheckoutRecord.status.in_(("pending", "inspection")),
                CheckoutRecord.expected_checkout_date.isnot(None),
                CheckoutRecord.expected_checkout_date < now.date(),
            )
        )
    ).all()
    ids: list[int] = []
    for co, emp in rows:
        alert = await wf.upsert_alert(
            db,
            alert_type="overdue_checkout",
            fingerprint=f"overdue_checkout:{co.id}",
            title=f"待退宿超期：{emp.full_name}（{emp.employee_no}）",
            detail=f"退宿单 {co.checkout_no} 超过预计退宿日 {co.expected_checkout_date}",
            severity="warning",
            employee_id=emp.id,
            accommodation_id=co.accommodation_id,
            business_type="checkout",
            business_id=co.id,
        )
        ids.append(alert.id)
    return ids


async def _scan_disabled_bed_occupied(db: AsyncSession) -> list[int]:
    rows = (
        await db.execute(
            select(AccommodationRecord, DormBed, Employee)
            .join(DormBed, DormBed.id == AccommodationRecord.bed_id)
            .join(Employee, Employee.id == AccommodationRecord.employee_id)
            .where(
                AccommodationRecord.status == "active",
                DormBed.operational_status.in_(("disabled", "maintenance")),
            )
        )
    ).all()
    ids: list[int] = []
    for acc, bed, emp in rows:
        alert = await wf.upsert_alert(
            db,
            alert_type="disabled_bed_occupied",
            fingerprint=f"disabled_bed_occupied:{bed.id}:{acc.id}",
            title=f"停用/维修床位仍有住户：{emp.full_name}",
            detail=(
                f"床位 {bed.bed_no} 状态为 {bed.operational_status}，"
                f"但住宿记录 {acc.id} 仍为 active"
            ),
            severity="warning",
            employee_id=emp.id,
            bed_id=bed.id,
            accommodation_id=acc.id,
            business_type="bed",
            business_id=bed.id,
        )
        ids.append(alert.id)
    return ids


async def _scan_reservation_overdue(db: AsyncSession, *, now: datetime) -> list[int]:
    rows = (
        await db.execute(
            select(BedReservation, Employee)
            .join(Employee, Employee.id == BedReservation.employee_id)
            .where(
                BedReservation.status == "active",
                BedReservation.expires_at.isnot(None),
                BedReservation.expires_at < now,
            )
        )
    ).all()
    ids: list[int] = []
    for res, emp in rows:
        alert = await wf.upsert_alert(
            db,
            alert_type="reservation_overdue",
            fingerprint=f"reservation_overdue:{res.id}",
            title=f"预留过期未入住：{emp.full_name}（{emp.employee_no}）",
            detail=f"床位预留 {res.reservation_no} 已过期（{res.expires_at}）",
            severity="warning",
            employee_id=emp.id,
            bed_id=res.bed_id,
            business_type="reservation",
            business_id=res.id,
        )
        ids.append(alert.id)
    return ids


async def run_all_scans(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """Full maintenance pass: expire reservations, then refresh alerts."""
    ts = now or utcnow()
    expiry = await expire_reservations(
        db, now=ts, actor_user_id=actor_user_id, request_id=request_id
    )
    alerts = await scan_alerts(
        db, now=ts, actor_user_id=actor_user_id, request_id=request_id
    )
    return {"expiry": expiry, "alerts": alerts, "ran_at": ts}
