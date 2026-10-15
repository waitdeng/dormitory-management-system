#!/usr/bin/env python3
"""HOTFIX-07 read-only classification of reserved applications without active reservation.

Never writes business data. Prints category counts + masked identifiers.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.accommodation import (  # noqa: E402
    AccommodationApplication,
    AccommodationRecord,
    BedReservation,
    CheckoutRecord,
    TransferRecord,
)
from app.models.employee import Employee  # noqa: E402


def mask(no: str | None) -> str:
    if not no:
        return "?"
    if len(no) <= 4:
        return "*" * len(no)
    return no[:2] + "*" * (len(no) - 4) + no[-2:]


async def run() -> int:
    cats: dict[str, list[str]] = {
        "C1_expired_no_active_accommodation": [],
        "C2_expired_but_employee_has_active_accommodation": [],
        "C3_expired_but_other_active_reservation_exists": [],
        "C4_has_transfer_or_checkout_or_reapply": [],
        "C5_manual_review": [],
    }

    async with AsyncSessionLocal() as db:
        apps = (
            await db.execute(
                select(AccommodationApplication)
                .where(AccommodationApplication.status == "reserved")
                .order_by(AccommodationApplication.id)
            )
        ).scalars().all()

        for app in apps:
            emp = (
                await db.execute(select(Employee).where(Employee.id == app.employee_id))
            ).scalar_one_or_none()
            tag = f"app#{app.id}/{app.application_no}/{mask(emp.employee_no if emp else None)}"

            my_res = (
                await db.execute(
                    select(BedReservation).where(BedReservation.application_id == app.id)
                )
            ).scalars().all()
            active_res = [r for r in my_res if r.status == "active"]
            if active_res:
                continue  # healthy reserved — not in the 109 set

            my_acc = (
                await db.execute(
                    select(AccommodationRecord).where(
                        AccommodationRecord.application_id == app.id
                    )
                )
            ).scalars().all()
            emp_active_acc = (
                await db.execute(
                    select(AccommodationRecord).where(
                        AccommodationRecord.employee_id == app.employee_id,
                        AccommodationRecord.status == "active",
                    )
                )
            ).scalars().first()
            other_res = (
                await db.execute(
                    select(BedReservation).where(
                        BedReservation.employee_id == app.employee_id,
                        BedReservation.status == "active",
                        BedReservation.application_id != app.id,
                    )
                )
            ).scalars().all()
            transfers = (
                await db.execute(
                    select(TransferRecord).where(TransferRecord.employee_id == app.employee_id)
                )
            ).scalars().all()
            checkouts = (
                await db.execute(
                    select(CheckoutRecord).where(CheckoutRecord.employee_id == app.employee_id)
                )
            ).scalars().all()
            later_apps = (
                await db.execute(
                    select(AccommodationApplication).where(
                        AccommodationApplication.employee_id == app.employee_id,
                        AccommodationApplication.id > app.id,
                    )
                )
            ).scalars().all()

            exp = [r for r in my_res if r.status == "expired"]
            detail = f"{tag}/res={[r.status for r in my_res]}/assigned={app.assigned_bed_id}"

            if transfers or checkouts or later_apps:
                cats["C4_has_transfer_or_checkout_or_reapply"].append(
                    detail + f"/tr={len(transfers)}/co={len(checkouts)}/later_apps={len(later_apps)}"
                )
            elif emp_active_acc is not None:
                cats["C2_expired_but_employee_has_active_accommodation"].append(
                    detail + f"/emp_active_acc={emp_active_acc.id}"
                )
            elif other_res:
                cats["C3_expired_but_other_active_reservation_exists"].append(
                    detail + f"/other_res={len(other_res)}"
                )
            elif exp and not my_acc and app.assigned_bed_id is not None:
                cats["C1_expired_no_active_accommodation"].append(detail)
            else:
                cats["C5_manual_review"].append(detail + f"/acc={len(my_acc)}")

    print("=== HOTFIX-07 read-only stale reserved classification ===")
    print(f"MYSQL_DATABASE={os.environ.get('MYSQL_DATABASE', '')}")
    total = 0
    for k, items in cats.items():
        total += len(items)
        print(f"\n[{k}] count={len(items)}")
        for line in items[:15]:
            print(f"  - {line}")
        if len(items) > 15:
            print(f"  ... {len(items) - 15} more")
    print(f"\nTOTAL_STALE={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
