"""HOTFIX-06 — check-in list bed association (real MySQL)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers_m2 import admin_headers
from tests.helpers_m3 import make_dorm, make_employee
from tests.helpers_m4 import checkin_employee


async def _list_apps(client, headers, **params):
    resp = await client.get("/api/v1/checkin-applications", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


@pytest.mark.asyncio
async def test_hotfix06_list_shows_bed_after_reserve_and_checkin(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="床位列")
    bed_no = dorm["beds"][0]["bed_no"]

    created = await client.post(
        "/api/v1/checkin-applications",
        headers=admin,
        json={"employee_id": emp["id"], "application_type": "new"},
    )
    app_id = created.json()["id"]

    # approved → 未分配 (bed null)
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=admin, json={})
    items = await _list_apps(client, admin, page=1, page_size=50, keyword=emp["employee_no"])
    row = next(r for r in items if r["id"] == app_id)
    assert row["status"] == "approved"
    assert row.get("bed") in (None, {})

    # reserved → full path
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=admin,
        json={"bed_id": dorm["beds"][0]["id"]},
    )
    items = await _list_apps(client, admin, page=1, page_size=50, keyword=emp["employee_no"])
    row = next(r for r in items if r["id"] == app_id)
    assert row["status"] == "reserved"
    assert row["bed"] is not None
    assert row["bed"]["bed_no"] == bed_no
    assert dorm["area"]["area_name"] in row["bed"]["bed_path"]
    assert str(dorm["floor"]["floor_no"]) in row["bed"]["bed_path"]

    # checked_in → still shows bed
    await client.post(f"/api/v1/checkin-applications/{app_id}/confirm", headers=admin, json={})
    items = await _list_apps(client, admin, page=1, page_size=50, keyword=emp["employee_no"])
    row = next(r for r in items if r["id"] == app_id)
    assert row["status"] == "checked_in"
    assert row["bed"] is not None
    assert row["bed"]["bed_no"] == bed_no

    # detail agrees with list
    detail = await client.get(f"/api/v1/checkin-applications/{app_id}", headers=admin)
    assert detail.json()["bed"]["bed_path"] == row["bed"]["bed_path"]


@pytest.mark.asyncio
async def test_hotfix06_list_matches_api_db_after_checkin(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="三层一致")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])

    items = await _list_apps(client, admin, page=1, page_size=50, keyword=emp["employee_no"])
    row = next(r for r in items if r["status"] == "checked_in")
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    target = next(b for b in beds if b["id"] == dorm["beds"][0]["id"])
    assert target["occupied"] is True
    assert row["bed"]["bed_no"] == target["bed_no"]
    assert row["bed"]["id"] == target["id"]


@pytest.mark.asyncio
async def test_hotfix06_after_transfer_shows_current_bed(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp = await make_employee(client, admin, suffix="调宿床位")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])

    tr = await client.post(
        "/api/v1/transfers",
        headers=admin,
        json={"employee_id": emp["id"], "target_bed_id": dorm["beds"][1]["id"], "reason": "t"},
    )
    tr_id = tr.json()["id"]
    await client.post(f"/api/v1/transfers/{tr_id}/reserve", headers=admin, json={})
    await client.post(f"/api/v1/transfers/{tr_id}/complete", headers=admin, json={})

    items = await _list_apps(client, admin, page=1, page_size=50, keyword=emp["employee_no"])
    row = next(r for r in items if r["status"] == "checked_in")
    assert row["bed"]["bed_no"] == dorm["beds"][1]["bed_no"]
    assert row["bed"]["bed_no"] != dorm["beds"][0]["bed_no"]


@pytest.mark.asyncio
async def test_hotfix06_expired_reservation_not_shown_as_active_bed(client: AsyncClient):
    """stale reserved + expired reservation → list must not pretend active bed."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="过期预留")
    created = await client.post(
        "/api/v1/checkin-applications",
        headers=admin,
        json={"employee_id": emp["id"], "application_type": "new"},
    )
    app_id = created.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=admin, json={})
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=admin,
        json={"bed_id": dorm["beds"][0]["id"], "expires_at": "2020-01-01T00:00:00"},
    )
    # run scanner to expire
    await client.post("/api/v1/scanner/run", headers=admin, json={})

    items = await _list_apps(client, admin, page=1, page_size=50, keyword=emp["employee_no"])
    row = next(r for r in items if r["id"] == app_id)
    # scanner returns app to approved + clears assigned bed
    assert row["status"] in {"approved", "reserved"}
    if row["status"] == "reserved":
        assert row.get("bed") is None
    else:
        assert row.get("bed") is None
