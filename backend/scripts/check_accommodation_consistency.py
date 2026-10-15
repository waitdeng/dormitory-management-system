#!/usr/bin/env python3
"""Read-only data consistency check (HOTFIX-06).

Scans MySQL for application / reservation / accommodation mismatches.
NEVER writes, deletes, or rebuilds business data.

Usage:
  cd backend && .venv/bin/python scripts/check_accommodation_consistency.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.accommodation import (  # noqa: E402
    AccommodationApplication,
    AccommodationRecord,
    BedReservation,
)
from app.models.employee import Employee  # noqa: E402


def mask_employee_no(no: str | None) -> str:
    if not no:
        return "?"
    if len(no) <= 4:
        return "*" * len(no)
    return no[:2] + "*" * (len(no) - 4) + no[-2:]


async def run() -> int:
    findings: dict[str, list[str]] = {
        "reserved_apps_without_active_reservation": [],
        "checked_in_apps_without_active_accommodation": [],
        "active_accommodation_without_bed": [],
        "bed_with_multiple_active_accommodations": [],
        "status_mismatch": [],
    }

    async with AsyncSessionLocal() as db:
        apps = (
            await db.execute(select(AccommodationApplication).order_by(AccommodationApplication.id))
        ).scalars().all()
        for app in apps:
            emp = (
                await db.execute(select(Employee).where(Employee.id == app.employee_id))
            ).scalar_one_or_none()
            tag = f"app#{app.id}/{app.application_no}/{mask_employee_no(emp.employee_no if emp else None)}"

            res = (
                await db.execute(
                    select(BedReservation).where(
                        BedReservation.application_id == app.id,
                        BedReservation.status == "active",
                    )
                )
            ).scalars().first()
            acc = (
                await db.execute(
                    select(AccommodationRecord).where(
                        AccommodationRecord.application_id == app.id,
                        AccommodationRecord.status == "active",
                    )
                )
            ).scalars().first()

            # reserved: must have active reservation OR be mid-confirm (active acc)
            if app.status == "reserved" and res is None and acc is None:
                any_res = (
                    await db.execute(
                        select(BedReservation).where(
                            BedReservation.application_id == app.id
                        )
                    )
                ).scalars().all()
                if any_res:
                    # expired/cancelled reservation but still status=reserved
                    findings["reserved_apps_without_active_reservation"].append(
                        f"{tag}/res_statuses={[r.status for r in any_res]}"
                    )
                else:
                    findings["reserved_apps_without_active_reservation"].append(tag)

            # checked_in: any accommodation row (active OR ended) proves history.
            # Ended-only is NORMAL after checkout — not an anomaly.
            if app.status == "checked_in":
                any_acc = (
                    await db.execute(
                        select(AccommodationRecord).where(
                            AccommodationRecord.application_id == app.id
                        )
                    )
                ).scalars().all()
                if not any_acc:
                    findings["checked_in_apps_without_active_accommodation"].append(tag)
                elif acc is None and all(a.status == "ended" for a in any_acc):
                    # checkout history — informational only
                    findings.setdefault("checked_in_with_ended_history_ok", []).append(tag)
            if app.status in {"reserved", "checked_in"} and app.assigned_bed_id is None:
                findings["status_mismatch"].append(f"{tag}/missing_assigned_bed_id")
            if app.status == "pending" and (res is not None or acc is not None):
                findings["status_mismatch"].append(f"{tag}/pending_has_active_records")
            if app.status == "reserved" and res and app.assigned_bed_id and res.bed_id != app.assigned_bed_id:
                findings["status_mismatch"].append(
                    f"app#{app.id}/assigned_bed={app.assigned_bed_id}/reserved_bed={res.bed_id}"
                )

        accs = (
            await db.execute(
                select(AccommodationRecord).where(AccommodationRecord.status == "active")
            )
        ).scalars().all()
        for rec in accs:
            emp = (
                await db.execute(select(Employee).where(Employee.id == rec.employee_id))
            ).scalar_one_or_none()
            tag = f"acc#{rec.id}/{mask_employee_no(emp.employee_no if emp else None)}"
            if rec.bed_id is None:
                findings["active_accommodation_without_bed"].append(tag)

        dup = await db.execute(
            select(AccommodationRecord.bed_id, func.count().label("cnt"))
            .where(AccommodationRecord.status == "active", AccommodationRecord.bed_id.is_not(None))
            .group_by(AccommodationRecord.bed_id)
            .having(func.count() > 1)
        )
        for bed_id, cnt in dup.all():
            findings["bed_with_multiple_active_accommodations"].append(f"bed#{bed_id}/cnt={cnt}")

        emp_dup = await db.execute(
            select(AccommodationRecord.employee_id, func.count().label("cnt"))
            .where(AccommodationRecord.status == "active")
            .group_by(AccommodationRecord.employee_id)
            .having(func.count() > 1)
        )
        for emp_id, cnt in emp_dup.all():
            findings["status_mismatch"].append(f"employee#{emp_id}/active_accommodations={cnt}")

    total = 0
    print("=== HOTFIX-06 read-only accommodation consistency check ===")
    print(f"env MYSQL_DATABASE={os.environ.get('MYSQL_DATABASE', '')}")
    for key, items in findings.items():
        if key.endswith("_ok"):
            print(f"\n[{key}] count={len(items)} (informational, not anomalies)")
            for line in items[:5]:
                print(f"  - {line}")
            continue
        total += len(items)
        print(f"\n[{key}] count={len(items)}")
        for line in items[:20]:
            print(f"  - {line}")
        if len(items) > 20:
            print(f"  ... {len(items) - 20} more")
    print(f"\nTOTAL_ANOMALIES={total}")
    return 0 if total == 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
