"""V1.0.1 GPT Web review remediation tests (real MySQL).

Covers:
  - FEAT-002: duplicate room / bad floor / leading-zero access code import
  - UX-004: partial failure recovery, no orphan reservations
  - FEAT-008: key separation + rotation decryptability, 403, export no leak
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from openpyxl import Workbook, load_workbook

from app.core.security import (
    decrypt_access_code,
    encrypt_access_code,
    reencrypt_access_code_token,
)
from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm, make_employee
from tests.helpers_m4 import headers_for_user, make_user_with_role


def _xlsx(headers: list[str], rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- FEAT-002 import edge cases ----------


@pytest.mark.asyncio
async def test_room_import_duplicate_and_bad_floor_and_leading_zero(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    area_code = dorm["area"]["area_code"]
    building_code = dorm["building"]["building_code"]
    floor_no = dorm["floor"]["floor_no"]
    room_no = unique_code("DUP")

    content = _xlsx(
        ["区域编码", "楼栋编码", "楼层号", "房间号", "房型编码", "容量", "性别政策", "门禁密码", "备注"],
        [
            # leading-zero door code as string
            [area_code, building_code, floor_no, room_no, "standard", 2, "any", "0012", "ok"],
            # duplicate room_no in same file
            [area_code, building_code, floor_no, room_no, "standard", 2, "any", "0013", "dup"],
            # bad floor
            [area_code, building_code, 9999, unique_code("X1"), "standard", 2, "any", None, "bad floor"],
            # capacity anomaly
            [area_code, building_code, floor_no, unique_code("X2"), "standard", 0, "any", None, "bad cap"],
        ],
    )
    preview = await client.post(
        "/api/v1/rooms/import/preview",
        headers=admin,
        files={"file": ("r.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200, preview.text
    rows = preview.json()["rows"]
    assert rows[0]["action"] == "create"
    assert rows[1]["action"] == "error"
    assert "重复" in (rows[1]["message"] or "")
    assert rows[2]["action"] == "error"
    assert rows[3]["action"] == "error"

    commit = await client.post(
        "/api/v1/rooms/import/commit",
        headers=admin,
        files={"file": ("r.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert commit.status_code == 200, commit.text
    assert commit.json()["summary"]["created"] == 1
    assert commit.json()["summary"]["failed"] == 3

    # leading-zero access code preserved
    rooms = await client.get(
        "/api/v1/rooms",
        headers=admin,
        params={"floor_id": dorm["floor"]["id"], "keyword": room_no},
    )
    hit = next(r for r in rooms.json()["items"] if r["room_no"] == room_no)
    assert hit["has_access_code"] is True
    reveal = await client.get(f"/api/v1/rooms/{hit['id']}/access-code", headers=admin)
    assert reveal.json()["access_code"] == "0012"


# ---------- FEAT-008 key separation / rotation ----------


def test_access_code_encrypt_decrypt_roundtrip_and_reencrypt():
    plain = "009876"
    token = encrypt_access_code(plain)
    assert token.startswith("v2:")
    assert decrypt_access_code(token) == plain
    rotated = reencrypt_access_code_token(token)
    assert rotated != token  # new ciphertext
    assert decrypt_access_code(rotated) == plain


def test_access_code_legacy_secret_key_still_decryptable(monkeypatch):
    """Ciphertext encrypted under SECRET_KEY-derived key remains readable after separation."""
    from app.core import security
    from app.core.config import settings

    legacy_plain = "00legacy"
    # simulate old token produced with SECRET_KEY-derived material
    old_token = "v1:" + security._fernet_from_material(
        settings.SECRET_KEY or "dev-only-insecure-secret"
    ).encrypt(legacy_plain.encode()).decode()

    # switch primary to a dedicated key
    monkeypatch.setattr(settings, "ACCESS_CODE_ENCRYPTION_KEY", "remediation-dedicated-key-material")
    monkeypatch.setattr(settings, "ACCESS_CODE_LEGACY_SECRETS", "SECRET_KEY")

    assert security.decrypt_access_code(old_token) == legacy_plain
    new_token = security.encrypt_access_code(legacy_plain)
    assert new_token.startswith("v2:")
    assert security.decrypt_access_code(new_token) == legacy_plain
    # rotated form still decrypts
    assert security.decrypt_access_code(security.reencrypt_access_code_token(old_token)) == legacy_plain


@pytest.mark.asyncio
async def test_access_code_rotate_endpoint_and_no_plaintext_in_list(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    room_id = dorm["room"]["id"]
    await client.put(
        f"/api/v1/rooms/{room_id}/access-code",
        headers=admin,
        json={"access_code": "003311"},
    )
    rot = await client.post("/api/v1/rooms/access-code/rotate", headers=admin, json={})
    assert rot.status_code == 200, rot.text
    body = rot.json()
    assert set(body) >= {"migrated", "already_current", "failed", "scanned"}
    assert "003311" not in str(body)

    listing = await client.get("/api/v1/rooms", headers=admin, params={"floor_id": dorm["floor"]["id"]})
    assert "003311" not in listing.text
    reveal = await client.get(f"/api/v1/rooms/{room_id}/access-code", headers=admin)
    assert reveal.json()["access_code"] == "003311"


@pytest.mark.asyncio
async def test_access_code_forbidden_without_permission(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    room_id = dorm["room"]["id"]
    await client.put(
        f"/api/v1/rooms/{room_id}/access-code",
        headers=admin,
        json={"access_code": "secret99"},
    )
    viewer = await make_user_with_role(client, admin, "finance_viewer", "acsec")
    vh = await headers_for_user(client, viewer["username"])
    r = await client.get(f"/api/v1/rooms/{room_id}/access-code", headers=vh)
    assert r.status_code == 403, r.text
    assert "secret99" not in r.text
    # cannot rotate either
    r2 = await client.post("/api/v1/rooms/access-code/rotate", headers=vh, json={})
    assert r2.status_code == 403, r2.text


@pytest.mark.asyncio
async def test_access_code_not_in_employee_or_report_export(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    await client.put(
        f"/api/v1/rooms/{dorm['room']['id']}/access-code",
        headers=admin,
        json={"access_code": "007777"},
    )
    emp_export = await client.get("/api/v1/employees/export", headers=admin)
    assert emp_export.status_code == 200
    assert b"007777" not in emp_export.content

    report_export = await client.get("/api/v1/reports/vacant-beds/export", headers=admin)
    assert report_export.status_code == 200
    assert b"007777" not in report_export.content

    rooms = await client.get("/api/v1/rooms", headers=admin, params={"floor_id": dorm["floor"]["id"]})
    assert "007777" not in rooms.text


# ---------- UX-004 batch allocation recovery ----------


@pytest.mark.asyncio
async def test_alloc_import_partial_failure_leaves_no_orphan_reservation(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp_ok = await make_employee(client, admin, suffix="批成功")
    emp_bad = await make_employee(client, admin, suffix="批失败")
    # make emp_bad ineligible AFTER preview would pass... actually
    # force failure by using a bed that exists but employee already housed later.
    # Simpler: second row uses employee that gets housing_required=false.
    await client.patch(
        f"/api/v1/employees/{emp_bad['id']}",
        headers=admin,
        json={"accommodation_required": False},
    )

    area_code = dorm["area"]["area_code"]
    building_code = dorm["building"]["building_code"]
    floor_no = dorm["floor"]["floor_no"]
    room_no = dorm["room"]["room_no"]
    bed1 = dorm["beds"][0]["bed_no"]
    bed2 = dorm["beds"][1]["bed_no"]

    content = _xlsx(
        ["员工工号", "区域编码", "楼栋编码", "楼层号", "房间号", "床位号"],
        [
            [emp_ok["employee_no"], area_code, building_code, floor_no, room_no, bed1],
            [emp_bad["employee_no"], area_code, building_code, floor_no, room_no, bed2],
        ],
    )
    commit = await client.post(
        "/api/v1/allocations/import/commit",
        headers=admin,
        files={"file": ("a.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert commit.status_code == 200, commit.text
    body = commit.json()
    assert body["summary"]["succeeded"] == 1
    assert body["summary"]["failed"] == 1
    # each row has explicit result + recovery marker
    for row in body["rows"]:
        assert row["action"] in {"success", "error", "allocate"}
        if row["action"] == "error":
            assert row["message"]
            assert row.get("recovery") is not None

    # bed2 must NOT be occupied or reserved
    beds = await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)
    by_no = {b["bed_no"]: b for b in beds.json()}
    assert by_no[bed2]["occupied"] is False
    assert by_no[bed2]["available"] is True
    # emp_bad has no active accommodation
    acc = await client.get(f"/api/v1/employees/{emp_bad['id']}/accommodation", headers=admin)
    assert acc.status_code in (200, 404)
    if acc.status_code == 200:
        payload = acc.json()
        assert not payload or payload.get("status") != "active"


@pytest.mark.asyncio
async def test_alloc_import_duplicate_submit_rejected_cleanly(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="重提")
    area_code = dorm["area"]["area_code"]
    building_code = dorm["building"]["building_code"]
    floor_no = dorm["floor"]["floor_no"]
    room_no = dorm["room"]["room_no"]
    bed_no = dorm["beds"][0]["bed_no"]

    content = _xlsx(
        ["员工工号", "区域编码", "楼栋编码", "楼层号", "房间号", "床位号"],
        [[emp["employee_no"], area_code, building_code, floor_no, room_no, bed_no]],
    )
    first = await client.post(
        "/api/v1/allocations/import/commit",
        headers=admin,
        files={"file": ("a.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert first.status_code == 200
    assert first.json()["summary"]["succeeded"] == 1

    second = await client.post(
        "/api/v1/allocations/import/commit",
        headers=admin,
        files={"file": ("a.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert second.status_code == 200, second.text
    # second batch must not double-assign
    assert second.json()["summary"]["succeeded"] == 0
    assert second.json()["summary"]["failed"] == 1

    beds = await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)
    assert beds.json()[0]["occupied"] is True
    assert beds.json()[0]["available"] is False


@pytest.mark.asyncio
async def test_alloc_import_concurrent_same_bed_only_one_wins(client: AsyncClient):
    import asyncio

    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp_a = await make_employee(client, admin, suffix="并发A")
    emp_b = await make_employee(client, admin, suffix="并发B")
    area_code = dorm["area"]["area_code"]
    building_code = dorm["building"]["building_code"]
    floor_no = dorm["floor"]["floor_no"]
    room_no = dorm["room"]["room_no"]
    bed_no = dorm["beds"][0]["bed_no"]

    def payload(emp_no: str) -> bytes:
        return _xlsx(
            ["员工工号", "区域编码", "楼栋编码", "楼层号", "房间号", "床位号"],
            [[emp_no, area_code, building_code, floor_no, room_no, bed_no]],
        )

    async def run_one(emp_no: str):
        return await client.post(
            "/api/v1/allocations/import/commit",
            headers=admin,
            files={
                "file": (
                    "a.xlsx",
                    payload(emp_no),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    r1, r2 = await asyncio.gather(run_one(emp_a["employee_no"]), run_one(emp_b["employee_no"]))
    assert r1.status_code == 200 and r2.status_code == 200
    s1 = r1.json()["summary"]["succeeded"]
    s2 = r2.json()["summary"]["succeeded"]
    assert s1 + s2 == 1, f"both succeeded? {s1} {s2}"

    beds = await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)
    assert beds.json()[0]["occupied"] is True
