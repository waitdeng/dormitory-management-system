"""V1.0.1 BUG-001 — safe delete of dorm resources (real MySQL)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm, make_employee
from tests.helpers_m4 import checkin_employee


@pytest.mark.asyncio
async def test_bug001_delete_unused_bed_ok(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    bed_id = dorm["beds"][0]["id"]
    resp = await client.delete(f"/api/v1/beds/{bed_id}", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True
    beds = await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)
    assert all(b["id"] != bed_id for b in beds.json())


@pytest.mark.asyncio
async def test_bug001_delete_bed_with_history_blocked(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="占床")
    await checkin_employee(client, admin, emp["id"], dorm["beds"][0]["id"])
    resp = await client.delete(f"/api/v1/beds/{dorm['beds'][0]['id']}", headers=admin)
    assert resp.status_code in (400, 422), resp.text
    message = resp.json().get("message", "")
    assert "不允许删除" in message or "关联" in message


@pytest.mark.asyncio
async def test_bug001_delete_room_with_beds_blocked(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    resp = await client.delete(f"/api/v1/rooms/{dorm['room']['id']}", headers=admin)
    assert resp.status_code in (400, 422), resp.text


@pytest.mark.asyncio
async def test_bug001_delete_room_empty_ok(client: AsyncClient):
    admin = await admin_headers(client)
    area = (
        await client.post(
            "/api/v1/dorm-areas",
            headers=admin,
            json={"area_code": unique_code("A"), "area_name": "删除测试区"},
        )
    ).json()
    building = (
        await client.post(
            "/api/v1/buildings",
            headers=admin,
            json={"area_id": area["id"], "building_code": unique_code("B"), "building_name": "删除楼"},
        )
    ).json()
    floor = (
        await client.post(
            "/api/v1/floors",
            headers=admin,
            json={"building_id": building["id"], "floor_no": 1},
        )
    ).json()
    room = (
        await client.post(
            "/api/v1/rooms",
            headers=admin,
            json={"floor_id": floor["id"], "room_no": unique_code("R"), "capacity": 1, "bed_count": 0},
        )
    ).json()
    # delete room with no beds
    resp = await client.delete(f"/api/v1/rooms/{room['id']}", headers=admin)
    assert resp.status_code == 200, resp.text
    # delete empty floor
    resp = await client.delete(f"/api/v1/floors/{floor['id']}", headers=admin)
    assert resp.status_code == 200, resp.text
    # delete empty building
    resp = await client.delete(f"/api/v1/buildings/{building['id']}", headers=admin)
    assert resp.status_code == 200, resp.text
    # delete empty area
    resp = await client.delete(f"/api/v1/dorm-areas/{area['id']}", headers=admin)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_bug001_delete_area_with_children_blocked(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    resp = await client.delete(f"/api/v1/dorm-areas/{dorm['area']['id']}", headers=admin)
    assert resp.status_code in (400, 422), resp.text
