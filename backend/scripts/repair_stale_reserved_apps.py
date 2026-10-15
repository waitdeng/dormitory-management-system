#!/usr/bin/env python3
"""HOTFIX-07 repair script (DRAFT — isolated DB drill only).

Safe-by-default design:
  * dry-run unless --apply
  * re-checks DB state at repair time (not analysis snapshot)
  * only touches status=reserved applications that have:
      - NO active reservation
      - NO active accommodation for the application
      - at least one reservation with status in (expired, cancelled) OR assigned_bed set
      - employee has NO active accommodation (no double-housing risk)
  * C5 (reserved + cancelled-only reservation) is excluded by default
  * never deletes reservation/accommodation history
  * per-row audit + before/after snapshot
  * idempotent: re-run finds nothing

Usage:
  python scripts/repair_stale_reserved_apps.py --dry-run
  python scripts/repair_stale_reserved_apps.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.accommodation import (  # noqa: E402
    AccommodationApplication,
    AccommodationRecord,
    BedReservation,
)
from app.models.employee import Employee  # noqa: E402
from app.services import audit_service  # noqa: E402


def mask(no: str | None) -> str:
    if not no:
        return "?"
    return no[:2] + "*" * max(0, len(no) - 4) + (no[-2:] if len(no) >= 4 else "")


async def repair(*, apply: bool) -> int:
    repaired = 0
    skipped = 0
    async with AsyncSessionLocal() as db:
        apps = (
            await db.execute(
                select(AccommodationApplication)
                .where(AccommodationApplication.status == "reserved")
                .order_by(AccommodationApplication.id)
            )
        ).scalars().all()
        for app in apps:
            # Re-check current state (repair-time guard)
            active_res = (
                await db.execute(
                    select(BedReservation).where(
                        BedReservation.application_id == app.id,
                        BedReservation.status == "active",
                    )
                )
            ).scalars().first()
            if active_res is not None:
                skipped += 1
                continue
            active_acc = (
                await db.execute(
                    select(AccommodationRecord).where(
                        AccommodationRecord.application_id == app.id,
                        AccommodationRecord.status == "active",
                    )
                )
            ).scalars().first()
            if active_acc is not None:
                skipped += 1
                continue
            emp_acc = (
                await db.execute(
                    select(AccommodationRecord).where(
                        AccommodationRecord.employee_id == app.employee_id,
                        AccommodationRecord.status == "active",
                    )
                )
            ).scalars().first()
            if emp_acc is not None:
                skipped += 1
                continue

            res_rows = (
                await db.execute(
                    select(BedReservation).where(
                        BedReservation.application_id == app.id
                    )
                )
            ).scalars().all()
            # C1 only: require at least one expired reservation for THIS app.
            # C5 (cancelled-only) and consumed-only must NOT enter via assigned_bed_id.
            has_expired = any(r.status == "expired" for r in res_rows)
            if not has_expired:
                skipped += 1
                continue
            if any(r.status == "active" for r in res_rows):
                skipped += 1
                continue

            emp = (
                await db.execute(select(Employee).where(Employee.id == app.employee_id))
            ).scalar_one_or_none()
            before = {
                "id": app.id,
                "status": app.status,
                "assigned_bed_id": app.assigned_bed_id,
                "res_statuses": [r.status for r in res_rows],
            }
            print(
                f"{'APPLY' if apply else 'DRY'} app#{app.id}/"
                f"{mask(emp.employee_no if emp else None)} before={before}"
            )
            if apply:
                # Conservative: return to approved WITHOUT clearing assigned_bed_id
                # (history pointer). Operators may clear later via normal cancel.
                app.status = "approved"
                await audit_service.write_audit(
                    db,
                    action="application.repair_stale_reserved",
                    resource_type="accommodation_application",
                    resource_id=app.id,
                    actor_user_id=None,
                    request_id="hotfix07-repair",
                    before_data=before,
                    after_data={"id": app.id, "status": "approved", "assigned_bed_id": app.assigned_bed_id},
                )
            repaired += 1
        if apply:
            await db.commit()
    print(f"repaired={repaired} skipped={skipped}")
    return repaired


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    raise SystemExit(asyncio.run(repair(apply=args.apply)) and 0)
