"""Shared helpers for M3 accommodation tests (real MySQL)."""

from __future__ import annotations

from tests.helpers_m2 import admin_headers, unique_code

__all__ = ["admin_headers", "unique_code", "make_employee", "make_bed", "make_dorm"]


async def make_employee(client, headers, *, suffix: str = "") -> dict:
    payload = {
        "employee_no": unique_code("E"),
        "full_name": f"测试员工{suffix}",
        "gender": "male",
        "employment_status": "active",
        "accommodation_required": True,
    }
    resp = await client.post("/api/v1/employees", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def make_dorm(client, headers, *, capacity: int = 2) -> dict:
    """Create area→building→floor→room with auto-generated beds."""
    area = (
        await client.post(
            "/api/v1/dorm-areas",
            headers=headers,
            json={"area_code": unique_code("AREA"), "area_name": "M3测试生活区"},
        )
    ).json()
    building = (
        await client.post(
            "/api/v1/buildings",
            headers=headers,
            json={
                "area_id": area["id"],
                "building_code": unique_code("BLD"),
                "building_name": "M3测试楼",
            },
        )
    ).json()
    floor = (
        await client.post(
            "/api/v1/floors",
            headers=headers,
            json={"building_id": building["id"], "floor_no": 1, "floor_name": "一层"},
        )
    ).json()
    room = (
        await client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "floor_id": floor["id"],
                "room_no": unique_code("R"),
                "capacity": capacity,
            },
        )
    ).json()
    beds = (
        await client.get(f"/api/v1/rooms/{room['id']}/beds", headers=headers)
    ).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    return {
        "area": area,
        "building": building,
        "floor": floor,
        "room": room,
        "beds": bed_list,
    }


async def make_bed(client, headers, room_id: int) -> dict:
    resp = await client.post(
        f"/api/v1/rooms/{room_id}/beds",
        headers=headers,
        json={"room_id": room_id, "bed_no": unique_code("B")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
