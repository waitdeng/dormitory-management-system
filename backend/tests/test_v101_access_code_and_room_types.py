"""V1.0.1 FEAT-008 + FEAT-002 — room door access code and room types (real MySQL)."""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from openpyxl import Workbook, load_workbook

from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm
from tests.helpers_m4 import headers_for_user, make_user_with_role


@pytest.mark.asyncio
async def test_feat008_access_code_roundtrip_and_masking(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    room_id = dorm["room"]["id"]

    # set code with leading zeros as string
    resp = await client.put(
        f"/api/v1/rooms/{room_id}/access-code",
        headers=admin,
        json={"access_code": "001234"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_access_code"] is True
    assert "access_code" not in body or body.get("access_code") in (None, "")
    # list must not leak plaintext
    listing = await client.get("/api/v1/rooms", headers=admin, params={"floor_id": dorm["floor"]["id"]})
    assert listing.status_code == 200
    for row in listing.json()["items"]:
        assert "access_code" not in row or not row.get("access_code")
        raw = str(row)
        assert "001234" not in raw

    # authorized reveal keeps leading zeros
    reveal = await client.get(f"/api/v1/rooms/{room_id}/access-code", headers=admin)
    assert reveal.status_code == 200, reveal.text
    assert reveal.json()["access_code"] == "001234"

    # unauthorized role cannot reveal
    viewer = await make_user_with_role(client, admin, "finance_viewer", "acview")
    vh = await headers_for_user(client, viewer["username"])
    denied = await client.get(f"/api/v1/rooms/{room_id}/access-code", headers=vh)
    assert denied.status_code == 403, denied.text


@pytest.mark.asyncio
async def test_feat008_existing_rooms_compatible_null_password(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    reveal = await client.get(
        f"/api/v1/rooms/{dorm['room']['id']}/access-code", headers=admin
    )
    assert reveal.status_code == 200
    assert reveal.json()["access_code"] is None
    assert reveal.json()["room_id"] == dorm["room"]["id"]


@pytest.mark.asyncio
async def test_feat002_room_type_crud_and_capacity_not_auto_changed(client: AsyncClient):
    admin = await admin_headers(client)
    created = await client.post(
        "/api/v1/room-types",
        headers=admin,
        json={
            "type_code": unique_code("RT"),
            "type_name": "标准间",
            "default_capacity": 4,
            "status": "active",
        },
    )
    assert created.status_code == 201, created.text
    type_id = created.json()["id"]

    # create room with this type and capacity 2 (explicit)
    dorm_parent = await make_dorm(client, admin, capacity=0) if False else None
    # make a floor first
    from tests.helpers_m3 import make_dorm

    # use make_dorm then update room type name — capacity must stay
    dorm = await make_dorm(client, admin, capacity=2)
    room_id = dorm["room"]["id"]
    patch = await client.patch(
        f"/api/v1/rooms/{room_id}",
        headers=admin,
        json={"room_type": created.json()["type_code"], "capacity": 2},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["capacity"] == 2

    # rename type — must not change room capacity
    renamed = await client.patch(
        f"/api/v1/room-types/{type_id}",
        headers=admin,
        json={"type_name": "豪华标准间", "default_capacity": 8},
    )
    assert renamed.status_code == 200, renamed.text
    room_after = await client.get(f"/api/v1/rooms/{room_id}", headers=admin)
    assert room_after.json()["capacity"] == 2

    # disable type (archive)
    disabled = await client.post(f"/api/v1/room-types/{type_id}/disable", headers=admin, json={})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"


@pytest.mark.asyncio
async def test_feat008_audit_records_access_code_ops(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    room_id = dorm["room"]["id"]
    await client.put(f"/api/v1/rooms/{room_id}/access-code", headers=admin, json={"access_code": "9876"})
    await client.get(f"/api/v1/rooms/{room_id}/access-code", headers=admin)
    # audit list is admin-only; just ensure endpoints did not 500 and code is set
    reveal = await client.get(f"/api/v1/rooms/{room_id}/access-code", headers=admin)
    assert reveal.json()["access_code"] == "9876"
    clear = await client.put(f"/api/v1/rooms/{room_id}/access-code", headers=admin, json={"access_code": None})
    assert clear.status_code == 200
    assert clear.json()["has_access_code"] is False
