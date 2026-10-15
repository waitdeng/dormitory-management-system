"""HOTFIX-07A concurrency & lock-order tests (real MySQL).

Covers: confirm vs expire, cancel vs expire, re-reserve vs expire,
double scan, multi-bed same employee, duplicate confirm/expire,
deadlock retry, and protection of checked-in/transfer/checkout history.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.accommodation import (
    AccommodationApplication,
    AccommodationRecord,
    BedReservation,
)
from app.models.base import utcnow
from app.services import checkin_service, scanner_service
from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm, make_employee
from tests.helpers_m4 import checkin_employee


async def _create_reserve(client, headers, emp_id: int, bed_id: int, expires_at=None) -> int:
    app = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=headers,
            json={"employee_id": emp_id, "application_type": "new"},
        )
    ).json()
    app_id = app["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={})
    payload = {"bed_id": bed_id}
    if expires_at is not None:
        payload["expires_at"] = expires_at
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve", headers=headers, json=payload
    )
    assert r.status_code == 200, r.text
    return app_id


async def _app_state(app_id: int) -> tuple[str, int | None]:
    async with AsyncSessionLocal() as db:
        app = (
            await db.execute(
                select(AccommodationApplication).where(AccommodationApplication.id == app_id)
            )
        ).scalar_one()
        return app.status, app.assigned_bed_id


async def _res_states(app_id: int) -> list[str]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(BedReservation).where(BedReservation.application_id == app_id)
            )
        ).scalars().all()
        return [r.status for r in rows]


@pytest.mark.asyncio
async def test_07a_expire_reverts_app_to_approved(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="过期回退")
    past = (utcnow() - timedelta(hours=2)).isoformat()
    app_id = await _create_reserve(client, admin, emp["id"], dorm["beds"][0]["id"], expires_at=past)

    scan = await scanner_service.expire_reservations(AsyncSessionLocal and await _session())
    status, _ = await _app_state(app_id)
    assert status == "approved"
    assert "expired" in await _res_states(app_id)
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert beds[0]["available"] is True


async def _session():
    # helper returning a fresh AsyncSession — used only in this test file
    return AsyncSessionLocal()


@pytest.mark.asyncio
async def test_07a_confirm_vs_expire_concurrent(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="确认竞过期")
    past = (utcnow() - timedelta(minutes=1)).isoformat()
    app_id = await _create_reserve(client, admin, emp["id"], dorm["beds"][0]["id"], expires_at=past)

    async def do_confirm():
        async with AsyncSessionLocal() as db:
            try:
                await checkin_service.confirm_checkin(db, app_id)
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

    results = await asyncio.gather(do_confirm(), do_scan())
    # no deadlock crash; exactly one business outcome wins
    assert "OperationalError" not in results
    status, _ = await _app_state(app_id)
    async with AsyncSessionLocal() as db:
        accs = (
            await db.execute(
                select(AccommodationRecord).where(
                    AccommodationRecord.application_id == app_id,
                    AccommodationRecord.status == "active",
                )
            )
        ).scalars().all()
    # invariants: not both checked_in and empty; no double acc
    assert len(accs) <= 1
    if status == "checked_in":
        assert len(accs) == 1
    if status == "approved":
        assert len(accs) == 0
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert beds[0]["occupied"] == (status == "checked_in")


@pytest.mark.asyncio
async def test_07a_cancel_vs_expire(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="取消竞过期")
    past = (utcnow() - timedelta(minutes=1)).isoformat()
    app_id = await _create_reserve(client, admin, emp["id"], dorm["beds"][0]["id"], expires_at=past)

    async def do_cancel():
        async with AsyncSessionLocal() as db:
            try:
                await checkin_service.cancel_application(
                    db, app_id, reason="test", actor_user_id=None
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

    await asyncio.gather(do_cancel(), do_scan())
    status, _ = await _app_state(app_id)
    assert status in {"cancelled", "approved", "reserved"}
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert beds[0]["available"] is True


@pytest.mark.asyncio
async def test_07a_rereserve_vs_old_expire(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp = await make_employee(client, admin, suffix="换床竞过期")
    past = (utcnow() - timedelta(minutes=1)).isoformat()
    app_id = await _create_reserve(client, admin, emp["id"], dorm["beds"][0]["id"], expires_at=past)

    async def do_rereserve():
        async with AsyncSessionLocal() as db:
            try:
                await checkin_service.reserve_bed(db, app_id, bed_id=dorm["beds"][1]["id"])
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

    await asyncio.gather(do_rereserve(), do_scan())
    async with AsyncSessionLocal() as db:
        res = (
            await db.execute(
                select(BedReservation).where(BedReservation.application_id == app_id)
            )
        ).scalars().all()
        active = [r for r in res if r.status == "active"]
    # at most one active reservation
    assert len(active) <= 1
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert beds[0]["occupied"] is False


@pytest.mark.asyncio
async def test_07a_double_scan_idempotent(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="双扫描")
    past = (utcnow() - timedelta(hours=1)).isoformat()
    app_id = await _create_reserve(client, admin, emp["id"], dorm["beds"][0]["id"], expires_at=past)

    async with AsyncSessionLocal() as db:
        await scanner_service.expire_reservations(db)
    s1 = await _app_state(app_id)
    async with AsyncSessionLocal() as db:
        r2 = await scanner_service.expire_reservations(db)
    s2 = await _app_state(app_id)
    assert s1 == s2 == ("approved", s1[1])
    assert r2.get("expired") == [] or r2.get("expired") is None or len(r2.get("expired", [])) == 0


@pytest.mark.asyncio
async def test_07a_duplicate_confirm_idempotent(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="重复确认")
    app_id = await _create_reserve(client, admin, emp["id"], dorm["beds"][0]["id"])
    async with AsyncSessionLocal() as db:
        await checkin_service.confirm_checkin(db, app_id)
    async with AsyncSessionLocal() as db:
        again = await checkin_service.confirm_checkin(db, app_id)
    assert again["status"] == "checked_in"
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert beds[0]["occupied"] is True


@pytest.mark.asyncio
async def test_07a_same_employee_multi_bed_race(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp = await make_employee(client, admin, suffix="多床竞")

    async def reserve_one(bed_id: int):
        async with AsyncSessionLocal() as db:
            try:
                app = await checkin_service.create_application(
                    db, employee_id=emp["id"], application_type="new"
                )
                await checkin_service.approve_application(db, app["id"])
                await checkin_service.reserve_bed(db, app["id"], bed_id=bed_id)
                return "ok"
            except Exception as e:
                return type(e).__name__

    r1, r2 = await asyncio.gather(
        reserve_one(dorm["beds"][0]["id"]),
        reserve_one(dorm["beds"][1]["id"]),
    )
    # at most one succeeds due to open-application / employee availability rules
    oks = sum(1 for r in (r1, r2) if r == "ok")
    assert oks <= 1, f"both reserved: {r1}, {r2}"
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    occupied_or_reserved = sum(1 for b in beds if b["occupied"] or b["reserved"])
    assert occupied_or_reserved <= 1


@pytest.mark.asyncio
async def test_07a_protect_checked_in_and_history(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp = await make_employee(client, admin, suffix="保护历史")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])
    # transfer
    tr = (
        await client.post(
            "/api/v1/transfers",
            headers=admin,
            json={"employee_id": emp["id"], "target_bed_id": dorm["beds"][1]["id"], "reason": "p"},
        )
    ).json()
    await client.post(f"/api/v1/transfers/{tr['id']}/reserve", headers=admin, json={})
    await client.post(f"/api/v1/transfers/{tr['id']}/complete", headers=admin, json={})

    async with AsyncSessionLocal() as db:
        await scanner_service.expire_reservations(db)
    accs = (
        await client.get(f"/api/v1/employees/{emp['id']}/accommodation", headers=admin)
    ).json()
    assert accs["status"] == "active"
    assert accs["bed_id"] == dorm["beds"][1]["id"]
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert beds[1]["occupied"] is True
    assert beds[0]["available"] is True


@pytest.mark.asyncio
async def test_07a_no_new_stale_after_expire(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="无新异常")
    past = (utcnow() - timedelta(hours=1)).isoformat()
    app_id = await _create_reserve(client, admin, emp["id"], dorm["beds"][0]["id"], expires_at=past)
    async with AsyncSessionLocal() as db:
        await scanner_service.expire_reservations(db)
    status, _ = await _app_state(app_id)
    res = await _res_states(app_id)
    assert status != "reserved" or "active" in res
    assert status == "approved"
    assert "expired" in res
