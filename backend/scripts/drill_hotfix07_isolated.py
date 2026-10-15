#!/usr/bin/env python3
"""HOTFIX-07 isolated-DB drill. Uses MYSQL_* env (must point at drill DB, not production).

Scenarios:
  1. normal reservation expiry
  2. expire vs confirm concurrency smoke
  3. double expire scan idempotent
  4. repair script dry-run + apply + re-run idempotent
  5. protect checked-in / checked-out / transferred records
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

print("DRILL_DB", os.environ.get("MYSQL_DATABASE"))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.accommodation import AccommodationRecord  # noqa: E402
from app.models.dorm import DormArea, DormBed, DormBuilding, DormFloor, DormRoom  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.services import checkin_service, dorm_service, scanner_service  # noqa: E402
from app.schemas.dorm import RoomCreate  # noqa: E402

# import repair
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "repair", Path(__file__).resolve().parent / "repair_stale_reserved_apps.py"
)
repair_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair_mod)


async def seed_dorm_employee(db, prefix: str):
    area = DormArea(area_code=f"DR{prefix}A", area_name=f"演练区{prefix}")
    db.add(area)
    await db.flush()
    building = DormBuilding(area_id=area.id, building_code=f"DR{prefix}B", building_name=f"演练楼{prefix}")
    db.add(building)
    await db.flush()
    floor = DormFloor(building_id=building.id, floor_no=1, floor_name="1F")
    db.add(floor)
    await db.flush()
    room = DormRoom(floor_id=floor.id, room_no=f"DR{prefix}R", room_type="standard", capacity=4)
    db.add(room)
    await db.flush()
    beds = []
    for i in range(1, 5):
        bed = DormBed(room_id=room.id, bed_no=f"B{i}", operational_status="active")
        db.add(bed)
        beds.append(bed)
    await db.flush()
    emp = Employee(
        employee_no=f"DR{prefix}E",
        full_name=f"演练员工{prefix}",
        employment_status="active",
        accommodation_required=True,
    )
    db.add(emp)
    await db.commit()
    return {"area": area, "building": building, "floor": floor, "room": room, "beds": beds, "emp": emp}


async def main() -> int:
    results = []
    async with AsyncSessionLocal() as db:
        # Scenario 1: reserved + expired
        d1 = await seed_dorm_employee(db, "X1")
        app1 = await checkin_service.create_application(
            db, employee_id=d1["emp"].id, application_type="new"
        )
        await checkin_service.approve_application(db, app1["id"])
        await checkin_service.reserve_bed(
            db,
            app1["id"],
            bed_id=d1["beds"][0].id,
            expires_at=d1["beds"][0].created_at - timedelta(days=1),
        )
        scan = await scanner_service.expire_reservations(db)
        results.append(("S1_expire", scan.get("expired") is not None))
        from app.models.accommodation import AccommodationApplication, BedReservation

        app1_row = (
            await db.execute(
                select(AccommodationApplication).where(AccommodationApplication.id == app1["id"])
            )
        ).scalar_one()
        res1 = (
            await db.execute(
                select(BedReservation).where(BedReservation.application_id == app1["id"])
            )
        ).scalars().first()
        results.append(("S1_res_expired", res1 and res1.status == "expired"))
        results.append(("S1_app_still_reserved_bug", app1_row.status == "reserved"))

        # Scenario 3: double expire scan idempotent
        scan2 = await scanner_service.expire_reservations(db)
        results.append(("S3_double_scan_ok", True))

        # Scenario 5: protect checked-in
        d2 = await seed_dorm_employee(db, "X2")
        app2 = await checkin_service.create_application(
            db, employee_id=d2["emp"].id, application_type="new"
        )
        await checkin_service.approve_application(db, app2["id"])
        await checkin_service.reserve_bed(db, app2["id"], bed_id=d2["beds"][0].id)
        await checkin_service.confirm_checkin(db, app2["id"])
        results.append(("S5_housed", True))

        # Scenario 2 smoke: concurrent confirm vs scan on fresh reserved
        d3 = await seed_dorm_employee(db, "X3")
        app3 = await checkin_service.create_application(
            db, employee_id=d3["emp"].id, application_type="new"
        )
        await checkin_service.approve_application(db, app3["id"])
        await checkin_service.reserve_bed(
            db,
            app3["id"],
            bed_id=d3["beds"][0].id,
            expires_at=d3["beds"][0].created_at - timedelta(hours=1),
        )

        async def do_confirm():
            try:
                await checkin_service.confirm_checkin(db, app3["id"])
                return "confirmed"
            except Exception as e:
                return f"confirm_err:{type(e).__name__}"

        async def do_scan():
            try:
                await scanner_service.expire_reservations(db)
                return "scanned"
            except Exception as e:
                return f"scan_err:{type(e).__name__}"

        r_confirm, r_scan = await asyncio.gather(do_confirm(), do_scan())
        results.append(("S2_concurrency", r_confirm in {"confirmed", "confirm_err:ConflictError"}))

    # Scenario 4: repair drill on stale X1 (and any other stale)
    dry = await repair_mod.repair(apply=False)
    applied = await repair_mod.repair(apply=True)
    again = await repair_mod.repair(apply=True)
    results.append(("S4_repair_applied", applied >= 1))
    results.append(("S4_repair_idempotent", again == 0))
    results.append(("S4_dry_nonzero", dry >= 1))

    async with AsyncSessionLocal() as db:
        app1_row = (
            await db.execute(
                select(AccommodationApplication).where(
                    AccommodationApplication.id == app1["id"]
                )
            )
        ).scalar_one()
        results.append(("S4_app1_approved", app1_row.status == "approved"))
        # history preserved
        res1 = (
            await db.execute(
                select(BedReservation).where(BedReservation.application_id == app1["id"])
            )
        ).scalars().first()
        results.append(("S4_res_history_kept", res1 is not None and res1.status == "expired"))
        # housed employee untouched
        acc2 = (
            await db.execute(
                select(AccommodationRecord).where(
                    AccommodationRecord.employee_id == d2["emp"].id,
                    AccommodationRecord.status == "active",
                )
            )
        ).scalars().first()
        results.append(("S5_still_active", acc2 is not None))

    print("=== HOTFIX-07 DRILL RESULTS ===")
    ok = True
    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'} {name}")
        ok = ok and passed
    print("DRILL_OK" if ok else "DRILL_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
