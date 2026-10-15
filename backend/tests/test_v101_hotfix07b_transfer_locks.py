"""HOTFIX-07B transfer lock-order concurrency review tests (real MySQL).

Does NOT change transfer state machine — only measures race safety and records
invariants after concurrent operations.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.accommodation import AccommodationRecord, BedReservation, TransferRecord
from app.services import checkin_service, scanner_service, transfer_service
from tests.helpers_m2 import admin_headers
from tests.helpers_m3 import make_dorm, make_employee
from tests.helpers_m4 import checkin_employee


@pytest.mark.asyncio
async def test_07b_transfer_complete_vs_checkout(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp = await make_employee(client, admin, suffix="调退竞")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])
    tr = (
        await client.post(
            "/api/v1/transfers",
            headers=admin,
            json={"employee_id": emp["id"], "target_bed_id": dorm["beds"][1]["id"], "reason": "x"},
        )
    ).json()
    await client.post(f"/api/v1/transfers/{tr['id']}/reserve", headers=admin, json={})
    co = (
        await client.post(
            "/api/v1/checkouts",
            headers=admin,
            json={"employee_id": emp["id"], "reason": "race"},
        )
    ).json()

    async def do_tr():
        async with AsyncSessionLocal() as db:
            try:
                await transfer_service.complete_transfer(db, tr["id"])
                return "ok"
            except Exception as e:
                return type(e).__name__

    async def do_co():
        async with AsyncSessionLocal() as db:
            try:
                from app.services import checkout_service

                await checkout_service.complete_checkout(db, co["id"])
                return "ok"
            except Exception as e:
                return type(e).__name__

    r1, r2 = await asyncio.gather(do_tr(), do_co())
    assert "OperationalError" not in (r1, r2)
    async with AsyncSessionLocal() as db:
        accs = (
            await db.execute(
                select(AccommodationRecord).where(
                    AccommodationRecord.employee_id == emp["id"],
                    AccommodationRecord.status == "active",
                )
            )
        ).scalars().all()
        assert len(accs) <= 1


@pytest.mark.asyncio
async def test_07b_transfer_reserve_vs_expire_scan(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp = await make_employee(client, admin, suffix="调扫竞")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])
    tr = (
        await client.post(
            "/api/v1/transfers",
            headers=admin,
            json={"employee_id": emp["id"], "target_bed_id": dorm["beds"][1]["id"], "reason": "x"},
        )
    ).json()

    async def do_res():
        async with AsyncSessionLocal() as db:
            try:
                from datetime import timedelta

                from app.models.base import utcnow

                await transfer_service.reserve_target(
                    db, tr["id"], expires_at=utcnow() - timedelta(minutes=1)
                )
                return "ok"
            except Exception as e:
                return type(e).__name__

    async def do_scan():
        async with AsyncSessionLocal() as db:
            try:
                await scanner_service.expire_reservations(db)
                return "ok"
            except Exception as e:
                return type(e).__name__

    await asyncio.gather(do_res(), do_scan())
    # at most one active transfer reservation
    async with AsyncSessionLocal() as db:
        res = (
            await db.execute(
                select(BedReservation).where(BedReservation.employee_id == emp["id"])
            )
        ).scalars().all()
        assert sum(1 for r in res if r.status == "active") <= 1
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert beds[0]["occupied"] is True  # source still housed


@pytest.mark.asyncio
async def test_07b_two_transfers_same_employee_race(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=3)
    emp = await make_employee(client, admin, suffix="双调竞")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])

    async def make_and_reserve(bed_id: int):
        async with AsyncSessionLocal() as db:
            try:
                tr = await transfer_service.create_transfer(
                    db, employee_id=emp["id"], target_bed_id=bed_id, reason="r"
                )
                await transfer_service.reserve_target(db, tr["id"])
                return "ok"
            except Exception as e:
                return type(e).__name__

    r1, r2 = await asyncio.gather(
        make_and_reserve(dorm["beds"][1]["id"]),
        make_and_reserve(dorm["beds"][2]["id"]),
    )
    oks = sum(1 for r in (r1, r2) if r == "ok")
    assert oks <= 1, f"two open transfers: {r1},{r2}"
    async with AsyncSessionLocal() as db:
        open_tr = (
            await db.execute(
                select(TransferRecord).where(
                    TransferRecord.employee_id == emp["id"],
                    TransferRecord.status.in_(("pending", "reserved")),
                )
            )
        ).scalars().all()
        assert len(open_tr) <= 1


@pytest.mark.asyncio
async def test_07b_transfer_history_preserved_after_scan(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp = await make_employee(client, admin, suffix="调历史")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])
    tr = (
        await client.post(
            "/api/v1/transfers",
            headers=admin,
            json={"employee_id": emp["id"], "target_bed_id": dorm["beds"][1]["id"], "reason": "h"},
        )
    ).json()
    await client.post(f"/api/v1/transfers/{tr['id']}/reserve", headers=admin, json={})
    await client.post(f"/api/v1/transfers/{tr['id']}/complete", headers=admin, json={})
    async with AsyncSessionLocal() as db:
        await scanner_service.expire_reservations(db)
    acc = (await client.get(f"/api/v1/employees/{emp['id']}/accommodation", headers=admin)).json()
    assert acc["status"] == "active"
    assert acc["bed_id"] == dorm["beds"][1]["id"]
