"""HOTFIX-04 backend tests — room type delete protection + allocation state machine (real MySQL)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm, make_employee
from tests.helpers_m4 import checkin_employee, headers_for_user, make_user_with_role


@pytest.mark.asyncio
async def test_fix010_delete_unreferenced_room_type(client: AsyncClient):
    admin = await admin_headers(client)
    created = await client.post(
        "/api/v1/room-types",
        headers=admin,
        json={
            "type_code": unique_code("RT"),
            "type_name": "临时房型",
            "default_capacity": 4,
            "status": "active",
        },
    )
    assert created.status_code == 201, created.text
    type_id = created.json()["id"]
    resp = await client.delete(f"/api/v1/room-types/{type_id}", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True
    types = (await client.get("/api/v1/room-types", headers=admin)).json()
    assert all(t["id"] != type_id for t in types)


@pytest.mark.asyncio
async def test_fix010_delete_referenced_room_type_blocked(client: AsyncClient):
    admin = await admin_headers(client)
    code = unique_code("RTR")
    created = await client.post(
        "/api/v1/room-types",
        headers=admin,
        json={"type_code": code, "type_name": "被引用房型", "default_capacity": 2, "status": "active"},
    )
    type_id = created.json()["id"]

    dorm = await make_dorm(client, admin, capacity=1)
    patch = await client.patch(
        f"/api/v1/rooms/{dorm['room']['id']}",
        headers=admin,
        json={"room_type": code},
    )
    assert patch.status_code == 200, patch.text

    resp = await client.delete(f"/api/v1/room-types/{type_id}", headers=admin)
    assert resp.status_code in (400, 422), resp.text
    assert "引用" in resp.json()["message"] or "停用" in resp.json()["message"]

    # disable still allowed
    dis = await client.post(f"/api/v1/room-types/{type_id}/disable", headers=admin, json={})
    assert dis.status_code == 200
    # historical room keeps type code
    room = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}", headers=admin)).json()
    assert room["room_type"] == code


@pytest.mark.asyncio
async def test_fix010_delete_room_type_requires_update_permission(client: AsyncClient):
    admin = await admin_headers(client)
    created = await client.post(
        "/api/v1/room-types",
        headers=admin,
        json={"type_code": unique_code("RTX"), "type_name": "无权删除", "default_capacity": 2},
    )
    type_id = created.json()["id"]
    viewer = await make_user_with_role(client, admin, "finance_viewer", "rtf")
    vh = await headers_for_user(client, viewer["username"])
    resp = await client.delete(f"/api/v1/room-types/{type_id}", headers=vh)
    assert resp.status_code == 403, resp.text
    # still exists
    types = (await client.get("/api/v1/room-types", headers=admin)).json()
    assert any(t["id"] == type_id for t in types)


@pytest.mark.asyncio
async def test_fix009_delete_bed_and_room_with_refs(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="热修占床")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])

    # cannot delete occupied bed
    r = await client.delete(f"/api/v1/beds/{dorm['beds'][0]['id']}", headers=admin)
    assert r.status_code in (400, 422)
    # cannot delete room with beds
    r2 = await client.delete(f"/api/v1/rooms/{dorm['room']['id']}", headers=admin)
    assert r2.status_code in (400, 422)


@pytest.mark.asyncio
async def test_ux012_allocation_state_machine_no_frontend_simulation(client: AsyncClient):
    """Direct API path used by the new confirm button still enforces state machine."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="点床分配")

    # empty employee list filter excludes no-housing
    emp_no = await client.post(
        "/api/v1/employees",
        headers=admin,
        json={
            "employee_no": unique_code("E"),
            "full_name": "不需住",
            "accommodation_required": False,
            "employment_status": "active",
        },
    )
    listing = await client.get(
        "/api/v1/employees",
        headers=admin,
        params={"accommodation_required": True, "accommodation_status": "not_in_dorm", "page_size": 100},
    )
    ids = {row["id"] for row in listing.json()["items"]}
    assert emp_no.json()["id"] not in ids

    # full allocate flow
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert beds[0]["occupied"] is True

    # second allocate same bed must fail
    emp2 = await make_employee(client, admin, suffix="点床B")
    app = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=admin,
            json={"employee_id": emp2["id"], "application_type": "new"},
        )
    ).json()
    await client.post(f"/api/v1/checkin-applications/{app['id']}/approve", headers=admin, json={})
    r = await client.post(
        f"/api/v1/checkin-applications/{app['id']}/reserve",
        headers=admin,
        json={"bed_id": dorm["beds"][0]["id"]},
    )
    assert r.status_code in (400, 409, 422), r.text
