"""V1.0.1 FEAT-002 room import + UX-004 batch allocation import (real MySQL)."""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from openpyxl import Workbook, load_workbook

from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm, make_employee


def _xlsx(headers: list[str], rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_feat002_room_import_preview_and_commit(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    area_code = dorm["area"]["area_code"]
    building_code = dorm["building"]["building_code"]
    floor_no = dorm["floor"]["floor_no"]
    room_no = unique_code("IMP")

    content = _xlsx(
        ["区域编码", "楼栋编码", "楼层号", "房间号", "房型编码", "容量", "性别政策", "门禁密码", "备注"],
        [
            [area_code, building_code, floor_no, room_no, "standard", 2, "any", "0042", "导入测试"],
            [area_code, building_code, floor_no, unique_code("BAD"), "standard", 0, "any", None, "容量异常"],
            ["NO_SUCH", building_code, floor_no, unique_code("X"), "standard", 2, "any", None, "坏区域"],
        ],
    )
    preview = await client.post(
        "/api/v1/rooms/import/preview",
        headers=admin,
        files={"file": ("rooms.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["summary"]["total"] == 3
    assert body["summary"]["create"] == 1
    assert body["summary"]["error"] == 2

    commit = await client.post(
        "/api/v1/rooms/import/commit",
        headers=admin,
        files={"file": ("rooms.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert commit.status_code == 200, commit.text
    assert commit.json()["summary"]["created"] == 1
    assert commit.json()["summary"]["failed"] == 2
    # created room keeps leading-zero access code
    rooms = await client.get(
        "/api/v1/rooms",
        headers=admin,
        params={"floor_id": dorm["floor"]["id"], "keyword": room_no},
    )
    found = [r for r in rooms.json()["items"] if r["room_no"] == room_no]
    assert found and found[0]["has_access_code"] is True


@pytest.mark.asyncio
async def test_ux004_alloc_import_partial_success(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp_ok = await make_employee(client, admin, suffix="导入OK")
    emp_no = await make_employee(client, admin, suffix="导入禁")
    # flip one employee to no-housing
    r = await client.patch(
        f"/api/v1/employees/{emp_no['id']}",
        headers=admin,
        json={"accommodation_required": False},
    )
    assert r.status_code == 200

    area_code = dorm["area"]["area_code"]
    building_code = dorm["building"]["building_code"]
    floor_no = dorm["floor"]["floor_no"]
    room_no = dorm["room"]["room_no"]
    bed_ok = dorm["beds"][0]["bed_no"]
    bed_other = dorm["beds"][1]["bed_no"]

    content = _xlsx(
        ["员工工号", "区域编码", "楼栋编码", "楼层号", "房间号", "床位号"],
        [
            [emp_ok["employee_no"], area_code, building_code, floor_no, room_no, bed_ok],
            [emp_no["employee_no"], area_code, building_code, floor_no, room_no, bed_other],
            ["NOT_EXIST", area_code, building_code, floor_no, room_no, bed_ok],
        ],
    )
    preview = await client.post(
        "/api/v1/allocations/import/preview",
        headers=admin,
        files={"file": ("a.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["error"] >= 2

    commit = await client.post(
        "/api/v1/allocations/import/commit",
        headers=admin,
        files={"file": ("a.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert commit.status_code == 200, commit.text
    summary = commit.json()["summary"]
    assert summary["succeeded"] == 1
    assert summary["failed"] == 2
    assert commit.json()["strategy"] == "partial_success_per_row"
    # row-level reasons present
    for row in commit.json()["rows"]:
        if row["action"] != "success":
            assert row["message"]
    # first employee is now housed
    acc = await client.get(f"/api/v1/employees/{emp_ok['id']}/accommodation", headers=admin)
    assert acc.status_code == 200
    assert acc.json()["status"] == "active"


@pytest.mark.asyncio
async def test_ux004_alloc_import_template(client: AsyncClient):
    admin = await admin_headers(client)
    resp = await client.get("/api/v1/allocations/import/template", headers=admin)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"
