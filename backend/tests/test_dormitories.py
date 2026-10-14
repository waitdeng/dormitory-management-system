"""Dormitory hierarchy and bed status integration tests (M2)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers_m2 import admin_headers, unique_code


async def _make_area(client: AsyncClient, headers: dict) -> dict:
    resp = await client.post(
        "/api/v1/dorm-areas",
        headers=headers,
        json={
            "area_code": unique_code("AREA"),
            "area_name": "测试生活区",
            "address": "测试路 1 号",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_dorm_hierarchy_crud(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    area = await _make_area(client, headers)
    building = await client.post(
        "/api/v1/buildings",
        headers=headers,
        json={
            "area_id": area["id"],
            "building_code": unique_code("BLD"),
            "building_name": "1 号楼",
            "total_floors": 3,
            "gender_policy": "male",
        },
    )
    assert building.status_code == 201, building.text
    building_id = building.json()["id"]

    # duplicate building code in same area -> 409
    dup_b = await client.post(
        "/api/v1/buildings",
        headers=headers,
        json={
            "area_id": area["id"],
            "building_code": building.json()["building_code"],
            "building_name": "重复楼",
        },
    )
    assert dup_b.status_code == 409

    floor = await client.post(
        "/api/v1/floors",
        headers=headers,
        json={"building_id": building_id, "floor_no": 1, "floor_name": "一层"},
    )
    assert floor.status_code == 201, floor.text
    floor_id = floor.json()["id"]

    # duplicate floor -> 409
    dup_f = await client.post(
        "/api/v1/floors",
        headers=headers,
        json={"building_id": building_id, "floor_no": 1},
    )
    assert dup_f.status_code == 409

    room = await client.post(
        "/api/v1/rooms",
        headers=headers,
        json={
            "floor_id": floor_id,
            "room_no": "101",
            "capacity": 4,
            "bed_count": 4,
            "gender_policy": "male",
        },
    )
    assert room.status_code == 201, room.text
    room_id = room.json()["id"]
    assert room.json()["bed_count"] == 4
    assert room.json()["capacity"] == 4

    beds = await client.get(f"/api/v1/rooms/{room_id}/beds", headers=headers)
    assert beds.status_code == 200
    assert len(beds.json()) == 4
    bed_ids = [b["id"] for b in beds.json()]

    # capacity 0 rejected
    bad_room = await client.post(
        "/api/v1/rooms",
        headers=headers,
        json={"floor_id": floor_id, "room_no": "102", "capacity": 0},
    )
    assert bad_room.status_code == 422

    # shrink capacity below bed count -> business rule
    shrink = await client.patch(
        f"/api/v1/rooms/{room_id}",
        headers=headers,
        json={"capacity": 2},
    )
    assert shrink.status_code == 422
    assert shrink.json()["code"] == "business_rule_violation"

    # bed disable / enable / maintenance
    bed_id = bed_ids[0]
    disabled = await client.post(f"/api/v1/beds/{bed_id}/disable", headers=headers)
    assert disabled.status_code == 200
    assert disabled.json()["operational_status"] == "disabled"
    assert disabled.json()["available"] is False

    maintained = await client.post(f"/api/v1/beds/{bed_id}/maintenance", headers=headers)
    assert maintained.status_code == 200
    assert maintained.json()["operational_status"] == "maintenance"

    enabled = await client.post(f"/api/v1/beds/{bed_id}/enable", headers=headers)
    assert enabled.status_code == 200
    assert enabled.json()["operational_status"] == "active"
    assert enabled.json()["available"] is True

    # cannot exceed capacity when adding beds
    extra = await client.post(
        f"/api/v1/rooms/{room_id}/beds",
        headers=headers,
        json={"room_id": room_id, "bed_no": "B99"},
    )
    assert extra.status_code == 422

    tree = await client.get("/api/v1/dormitories/tree", headers=headers)
    assert tree.status_code == 200
    assert area["area_code"] in tree.text

    available = await client.get(
        "/api/v1/beds/available",
        headers=headers,
        params={"building_id": building_id},
    )
    assert available.status_code == 200
    assert len(available.json()) >= 3

    occupancy = await client.get(
        f"/api/v1/buildings/{building_id}/occupancy", headers=headers
    )
    assert occupancy.status_code == 200
    assert occupancy.json()["bed_count"] == 4
    assert occupancy.json()["available_bed_count"] == 4
    # M2: no occupancy data yet
    assert occupancy.json()["occupied_bed_count"] == 0


@pytest.mark.asyncio
async def test_disabled_parent_blocks_new_children(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    area = await _make_area(client, headers)
    # disable area
    upd = await client.patch(
        f"/api/v1/dorm-areas/{area['id']}",
        headers=headers,
        json={"status": "disabled"},
    )
    assert upd.status_code == 200

    building = await client.post(
        "/api/v1/buildings",
        headers=headers,
        json={
            "area_id": area["id"],
            "building_code": unique_code("BLD"),
            "building_name": "禁用区新楼",
        },
    )
    assert building.status_code in {400, 422}
    assert building.json()["code"] in {"validation_error", "business_rule_violation"}
