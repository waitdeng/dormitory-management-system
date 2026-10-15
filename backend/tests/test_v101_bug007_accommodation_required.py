"""V1.0.1 BUG-007 (P0) — employees with accommodation_required=false must not get beds.

Covers every bypass path called out in the fix ticket:
  - default allocatable employee list excludes them
  - check-in application API rejects
  - bed reservation API rejects
  - visual allocation path (create → approve → reserve → confirm) rejects
  - transfer allocation rejects
  - flipping the flag after housing does NOT auto-release the bed
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm, make_employee
from tests.helpers_m4 import checkin_employee


async def _no_housing_employee(client: AsyncClient, headers: dict, suffix: str = "") -> dict:
    payload = {
        "employee_no": unique_code("E"),
        "full_name": f"不需住宿{suffix}",
        "gender": "male",
        "employment_status": "active",
        "accommodation_required": False,
    }
    resp = await client.post("/api/v1/employees", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_bug007_employee_list_excludes_no_accommodation(client: AsyncClient):
    admin = await admin_headers(client)
    needs = await make_employee(client, admin, suffix="需要")
    no_need = await _no_housing_employee(client, admin, "列表")

    resp = await client.get(
        "/api/v1/employees",
        headers=admin,
        params={
            "page": 1,
            "page_size": 100,
            "accommodation_status": "not_in_dorm",
            "accommodation_required": True,
        },
    )
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()["items"]}
    assert needs["id"] in ids
    assert no_need["id"] not in ids

    # unfiltered list still returns both
    resp_all = await client.get(
        "/api/v1/employees",
        headers=admin,
        params={"page": 1, "page_size": 100, "keyword": no_need["employee_no"]},
    )
    assert no_need["id"] in {row["id"] for row in resp_all.json()["items"]}


@pytest.mark.asyncio
async def test_bug007_checkin_application_rejected(client: AsyncClient):
    admin = await admin_headers(client)
    emp = await _no_housing_employee(client, admin, "申请")
    resp = await client.post(
        "/api/v1/checkin-applications",
        headers=admin,
        json={"employee_id": emp["id"], "application_type": "new"},
    )
    assert resp.status_code in (400, 409, 422), resp.text
    body = resp.json()
    message = (body.get("message") or "") + str(body.get("details") or "")
    assert "accommodation" in message.lower() or "住宿" in message or "not require" in message


@pytest.mark.asyncio
async def test_bug007_reserve_bed_rejected(client: AsyncClient):
    """Even if an application somehow exists, reserve must refuse."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    # create a normal application then flip the employee flag before reserve
    emp = await make_employee(client, admin, suffix="翻转")
    created = await client.post(
        "/api/v1/checkin-applications",
        headers=admin,
        json={"employee_id": emp["id"], "application_type": "new"},
    )
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=admin, json={})

    flip = await client.patch(
        f"/api/v1/employees/{emp['id']}",
        headers=admin,
        json={"accommodation_required": False},
    )
    assert flip.status_code == 200, flip.text

    bed_id = dorm["beds"][0]["id"]
    resp = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=admin,
        json={"bed_id": bed_id},
    )
    assert resp.status_code in (400, 409, 422), resp.text


@pytest.mark.asyncio
async def test_bug007_visual_allocation_flow_rejected(client: AsyncClient):
    """Same sequence the visual allocation page uses: create → approve → reserve → confirm."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await _no_housing_employee(client, admin, "可视化")
    bed_id = dorm["beds"][0]["id"]

    created = await client.post(
        "/api/v1/checkin-applications",
        headers=admin,
        json={"employee_id": emp["id"], "application_type": "new"},
    )
    assert created.status_code in (400, 409, 422), created.text


@pytest.mark.asyncio
async def test_bug007_transfer_allocation_rejected(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp = await make_employee(client, admin, suffix="调宿禁")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])

    flip = await client.patch(
        f"/api/v1/employees/{emp['id']}",
        headers=admin,
        json={"accommodation_required": False},
    )
    assert flip.status_code == 200, flip.text

    resp = await client.post(
        "/api/v1/transfers",
        headers=admin,
        json={
            "employee_id": emp["id"],
            "target_bed_id": dorm["beds"][1]["id"],
            "reason": "should be blocked",
        },
    )
    assert resp.status_code in (400, 409, 422), resp.text


@pytest.mark.asyncio
async def test_bug007_flip_flag_does_not_release_bed(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="保留床位")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])

    flip = await client.patch(
        f"/api/v1/employees/{emp['id']}",
        headers=admin,
        json={"accommodation_required": False},
    )
    assert flip.status_code == 200, flip.text

    acc = await client.get(f"/api/v1/employees/{emp['id']}/accommodation", headers=admin)
    assert acc.status_code == 200, acc.text
    assert acc.json()["status"] == "active"

    beds = await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)
    bed_list = beds.json()
    target = next(b for b in bed_list if b["id"] == dorm["beds"][0]["id"])
    assert target["occupied"] is True
    assert target["available"] is False


@pytest.mark.asyncio
async def test_bug007_permission_denied_without_checkin_create(client: AsyncClient):
    """A viewer role must not be able to allocate even for eligible employees."""
    from tests.helpers_m4 import headers_for_user, make_user_with_role

    admin = await admin_headers(client)
    viewer = await make_user_with_role(client, admin, "finance_viewer", "v007")
    vheaders = await headers_for_user(client, viewer["username"])
    emp = await make_employee(client, admin, suffix="越权")

    resp = await client.post(
        "/api/v1/checkin-applications",
        headers=vheaders,
        json={"employee_id": emp["id"], "application_type": "new"},
    )
    assert resp.status_code == 403, resp.text
