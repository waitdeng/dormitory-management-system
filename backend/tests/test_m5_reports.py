"""M5 reports & dashboard consistency tests (real MySQL).

Checks AGENTS.md §四 报表一致性要求 against real records.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm
from tests.helpers_m4 import checkin_employee


async def _dept(client, headers, name: str) -> dict:
    r = await client.post(
        "/api/v1/departments",
        headers=headers,
        json={"department_code": unique_code("D"), "department_name": name},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _emp(client, headers, dept_id: int | None, suffix: str = "") -> dict:
    r = await client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "employee_no": unique_code("E"),
            "full_name": f"报表员工{suffix}",
            "gender": "male",
            "employment_status": "active",
            "accommodation_required": True,
            "department_id": dept_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_dashboard_summary_matches_bed_flags(client: AsyncClient):
    """Vacant/occupied/reserved must match authoritative records."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=4)
    beds = dorm["beds"]
    assert len(beds) == 4

    emp1 = await _emp(client, admin, None, "1")
    emp2 = await _emp(client, admin, None, "2")

    # occupy bed0, reserve bed1, leave bed2 free, disable bed3
    await checkin_employee(client, admin, emp1["id"], beds[0]["id"])
    app2 = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=admin,
            json={"employee_id": emp2["id"], "application_type": "new"},
        )
    ).json()
    await client.post(
        f"/api/v1/checkin-applications/{app2['id']}/approve", headers=admin, json={}
    )
    r = await client.post(
        f"/api/v1/checkin-applications/{app2['id']}/reserve",
        headers=admin,
        json={"bed_id": beds[1]["id"]},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/beds/{beds[3]['id']}/disable", headers=admin, json={}
    )
    assert r.status_code == 200, r.text

    summary = (await client.get("/api/v1/dashboard/summary", headers=admin)).json()

    # room-level beds may exist in other tests' data; check local beds via vacant report
    vacant = await client.get(
        f"/api/v1/reports/vacant-beds?building_id={dorm['building']['id']}",
        headers=admin,
    )
    assert vacant.status_code == 200
    vacant_ids = {i["bed_id"] for i in vacant.json()["items"]}
    # bed2 is free and active
    assert beds[2]["id"] in vacant_ids
    # bed0 occupied, bed1 reserved, bed3 disabled → not vacant
    assert beds[0]["id"] not in vacant_ids
    assert beds[1]["id"] not in vacant_ids
    assert beds[3]["id"] not in vacant_ids

    # bed flags via rooms API
    room_beds = (
        await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)
    ).json()
    bed_list = room_beds["items"] if isinstance(room_beds, dict) else room_beds
    by_id = {b["id"]: b for b in bed_list}
    assert by_id[beds[0]["id"]]["occupied"] is True
    assert by_id[beds[1]["id"]]["reserved"] is True
    assert by_id[beds[2]["id"]]["occupied"] is False
    assert by_id[beds[2]["id"]]["reserved"] is False
    assert by_id[beds[3]["id"]]["operational_status"] == "disabled"

    assert summary["bed_total"] >= 4
    assert summary["vacant_beds"] >= 1


@pytest.mark.asyncio
async def test_accommodation_ledger_matches_active_records(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp = await _emp(client, admin, None, "L")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])

    ledger = (await client.get("/api/v1/reports/accommodations", headers=admin)).json()
    rows = [i for i in ledger["items"] if i["employee_id"] == emp["id"]]
    assert len(rows) == 1
    assert rows[0]["bed_id"] == dorm["beds"][0]["id"]
    assert rows[0]["employee_no"] == emp["employee_no"]

    # terminated but still housed still counts
    await client.post(f"/api/v1/employees/{emp['id']}/terminate", headers=admin, json={})
    ledger2 = (await client.get("/api/v1/reports/accommodations", headers=admin)).json()
    rows2 = [i for i in ledger2["items"] if i["employee_id"] == emp["id"]]
    assert len(rows2) == 1
    assert rows2[0]["employment_status"] == "terminated"

    summary = (await client.get("/api/v1/dashboard/summary", headers=admin)).json()
    assert summary["terminated_still_housed"] >= 1


@pytest.mark.asyncio
async def test_reserved_bed_not_counted_as_vacant(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    bed = dorm["beds"][0]
    emp = await _emp(client, admin, None, "R")
    app = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=admin,
            json={"employee_id": emp["id"], "application_type": "new"},
        )
    ).json()
    await client.post(
        f"/api/v1/checkin-applications/{app['id']}/approve", headers=admin, json={}
    )
    await client.post(
        f"/api/v1/checkin-applications/{app['id']}/reserve",
        headers=admin,
        json={"bed_id": bed["id"]},
    )

    vacant = (
        await client.get(
            f"/api/v1/reports/vacant-beds?building_id={dorm['building']['id']}",
            headers=admin,
        )
    ).json()
    assert bed["id"] not in {i["bed_id"] for i in vacant["items"]}


@pytest.mark.asyncio
async def test_maintenance_and_disabled_beds_not_allocatable(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    b0, b1 = dorm["beds"]
    await client.post(f"/api/v1/beds/{b0['id']}/maintenance", headers=admin, json={})
    await client.post(f"/api/v1/beds/{b1['id']}/disable", headers=admin, json={})

    vacant = (
        await client.get(
            f"/api/v1/reports/vacant-beds?building_id={dorm['building']['id']}",
            headers=admin,
        )
    ).json()
    ids = {i["bed_id"] for i in vacant["items"]}
    assert b0["id"] not in ids
    assert b1["id"] not in ids


@pytest.mark.asyncio
async def test_reports_export_and_transfer_history(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp = await _emp(client, admin, None, "T")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])

    # transfer to bed1
    r = await client.post(
        "/api/v1/transfers",
        headers=admin,
        json={
            "employee_id": emp["id"],
            "target_bed_id": dorm["beds"][1]["id"],
            "reason": "调宿测试",
        },
    )
    assert r.status_code == 201, r.text
    transfer_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/transfers/{transfer_id}/reserve",
        headers=admin,
        json={"target_bed_id": dorm["beds"][1]["id"]},
    )
    assert r.status_code in (200, 409), r.text
    if r.status_code == 200:
        r = await client.post(
            f"/api/v1/transfers/{transfer_id}/complete", headers=admin, json={}
        )
        assert r.status_code == 200, r.text

    transfers = (await client.get("/api/v1/reports/transfers", headers=admin)).json()
    assert transfers["total"] >= 1
    assert any(i["employee_id"] == emp["id"] for i in transfers["items"])

    # export all report types
    for rt in (
        "accommodations",
        "vacant-beds",
        "departments",
        "checkin-checkout",
        "transfers",
        "exceptions",
    ):
        resp = await client.get(f"/api/v1/reports/{rt}/export", headers=admin)
        assert resp.status_code == 200, (rt, resp.text)
        assert resp.content[:2] == b"PK", rt


@pytest.mark.asyncio
async def test_checkin_checkout_report_contains_events(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await _emp(client, admin, None, "C")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])

    r = await client.post(
        "/api/v1/checkouts",
        headers=admin,
        json={"employee_id": emp["id"], "checkout_type": "normal"},
    )
    assert r.status_code == 201, r.text
    co_id = r.json()["id"]
    r = await client.post(f"/api/v1/checkouts/{co_id}/complete", headers=admin, json={})
    assert r.status_code == 200, r.text

    events = (
        await client.get("/api/v1/reports/checkin-checkout", headers=admin)
    ).json()
    types = {i["event_type"] for i in events["items"] if i["employee_id"] == emp["id"]}
    assert "checkin" in types
    assert "checkout" in types
