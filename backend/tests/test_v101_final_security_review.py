"""V1.0.1 final security review — UX-004 failure recovery + FEAT-008 rotate authz.

Real MySQL. Injected failures via monkeypatch of checkin_service entry points.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from app.services import checkin_service
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


async def _alloc_payload(client, headers, emp, dorm, bed_no=None) -> bytes:
    return _xlsx(
        ["员工工号", "区域编码", "楼栋编码", "楼层号", "房间号", "床位号"],
        [
            [
                emp["employee_no"],
                dorm["area"]["area_code"],
                dorm["building"]["building_code"],
                dorm["floor"]["floor_no"],
                dorm["room"]["room_no"],
                bed_no or dorm["beds"][0]["bed_no"],
            ]
        ],
    )


async def _post_alloc(client, headers, content: bytes):
    return await client.post(
        "/api/v1/allocations/import/commit",
        headers=headers,
        files={
            "file": (
                "a.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def _bed_flags(beds_json, bed_no: str) -> dict:
    return next(b for b in beds_json if b["bed_no"] == bed_no)


# ========== UX-004 failure recovery ==========


@pytest.mark.asyncio
async def test_ux004_reserve_fails_after_application(client: AsyncClient, monkeypatch):
    """Application created+approved, reserve fails → no leftover active reservation."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="预留失败")
    content = await _alloc_payload(client, admin, emp, dorm)

    orig_reserve = checkin_service.reserve_bed

    async def boom_reserve(*args, **kwargs):
        raise RuntimeError("injected reserve failure")

    monkeypatch.setattr(checkin_service, "reserve_bed", boom_reserve)
    resp = await _post_alloc(client, admin, content)
    monkeypatch.setattr(checkin_service, "reserve_bed", orig_reserve)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["succeeded"] == 0
    assert body["summary"]["failed"] == 1
    row = body["rows"][0]
    assert row["action"] == "error"
    assert "injected reserve failure" in (row["message"] or "")
    assert row["recovery"] in {
        "application_cancelled",
        "reservation_released",
        "rollback_only",
    } or str(row["recovery"]).startswith("cancel_failed")

    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    flags = _bed_flags(beds, dorm["beds"][0]["bed_no"])
    assert flags["occupied"] is False
    assert flags["reserved"] is False
    assert flags["available"] is True

    acc = await client.get(f"/api/v1/employees/{emp['id']}/accommodation", headers=admin)
    assert acc.status_code != 200 or not acc.json() or acc.json().get("status") != "active"


@pytest.mark.asyncio
async def test_ux004_confirm_fails_after_reserve(client: AsyncClient, monkeypatch):
    """Reserve succeeded, confirm fails → reservation must not stay active."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="确认失败")
    content = await _alloc_payload(client, admin, emp, dorm)

    orig_confirm = checkin_service.confirm_checkin

    async def boom_confirm(*args, **kwargs):
        raise RuntimeError("injected confirm failure")

    monkeypatch.setattr(checkin_service, "confirm_checkin", boom_confirm)
    resp = await _post_alloc(client, admin, content)
    monkeypatch.setattr(checkin_service, "confirm_checkin", orig_confirm)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["succeeded"] == 0
    assert body["summary"]["failed"] == 1
    row = body["rows"][0]
    assert row["action"] == "error"
    assert "injected confirm failure" in (row["message"] or "")
    assert row["recovery"] in {"application_cancelled", "reservation_released"}

    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    flags = _bed_flags(beds, dorm["beds"][0]["bed_no"])
    assert flags["occupied"] is False
    assert flags["reserved"] is False, "orphan active reservation left behind"
    assert flags["available"] is True


@pytest.mark.asyncio
async def test_ux004_cancel_fails_then_orphan_reservation_released(
    client: AsyncClient, monkeypatch
):
    """If cancel_application fails, force-release leftover reservations."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="取消失败")
    content = await _alloc_payload(client, admin, emp, dorm)

    orig_confirm = checkin_service.confirm_checkin
    orig_cancel = checkin_service.cancel_application

    async def boom_confirm(*args, **kwargs):
        raise RuntimeError("injected confirm failure")

    async def boom_cancel(*args, **kwargs):
        raise RuntimeError("injected cancel failure")

    monkeypatch.setattr(checkin_service, "confirm_checkin", boom_confirm)
    monkeypatch.setattr(checkin_service, "cancel_application", boom_cancel)
    resp = await _post_alloc(client, admin, content)
    monkeypatch.setattr(checkin_service, "confirm_checkin", orig_confirm)
    monkeypatch.setattr(checkin_service, "cancel_application", orig_cancel)

    assert resp.status_code == 200, resp.text
    row = resp.json()["rows"][0]
    assert row["action"] == "error"
    # recovery must be explicit — either orphan released or cancel_failed marker
    assert row["recovery"] in {"reservation_released"} or str(row["recovery"]).startswith(
        "cancel_failed"
    )

    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    flags = _bed_flags(beds, dorm["beds"][0]["bed_no"])
    assert flags["occupied"] is False
    assert flags["reserved"] is False, "cancel failure left an unexplained active reservation"


@pytest.mark.asyncio
async def test_ux004_db_exception_mid_batch_leaves_prior_success_intact(
    client: AsyncClient, monkeypatch
):
    """DB/app exception on row 2 must not undo row 1 success nor double-occupy."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    emp1 = await make_employee(client, admin, suffix="批1成功")
    emp2 = await make_employee(client, admin, suffix="批2异常")

    content = _xlsx(
        ["员工工号", "区域编码", "楼栋编码", "楼层号", "房间号", "床位号"],
        [
            [
                emp1["employee_no"],
                dorm["area"]["area_code"],
                dorm["building"]["building_code"],
                dorm["floor"]["floor_no"],
                dorm["room"]["room_no"],
                dorm["beds"][0]["bed_no"],
            ],
            [
                emp2["employee_no"],
                dorm["area"]["area_code"],
                dorm["building"]["building_code"],
                dorm["floor"]["floor_no"],
                dorm["room"]["room_no"],
                dorm["beds"][1]["bed_no"],
            ],
        ],
    )

    orig_create = checkin_service.create_application
    calls = {"n": 0}

    async def flaky_create(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("injected db exception")
        return await orig_create(*args, **kwargs)

    monkeypatch.setattr(checkin_service, "create_application", flaky_create)
    resp = await _post_alloc(client, admin, content)
    monkeypatch.setattr(checkin_service, "create_application", orig_create)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["succeeded"] == 1
    assert body["summary"]["failed"] == 1
    assert body["rows"][0]["action"] == "success"
    assert body["rows"][1]["action"] == "error"
    assert "injected db exception" in (body["rows"][1]["message"] or "")

    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert _bed_flags(beds, dorm["beds"][0]["bed_no"])["occupied"] is True
    b2 = _bed_flags(beds, dorm["beds"][1]["bed_no"])
    assert b2["occupied"] is False
    assert b2["available"] is True


@pytest.mark.asyncio
async def test_ux004_duplicate_import_retry_does_not_reassign(client: AsyncClient):
    """Same import committed twice: second run must not create a second occupancy."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await make_employee(client, admin, suffix="重试不双占")
    content = await _alloc_payload(client, admin, emp, dorm)

    first = await _post_alloc(client, admin, content)
    assert first.json()["summary"]["succeeded"] == 1

    second = await _post_alloc(client, admin, content)
    assert second.status_code == 200
    assert second.json()["summary"]["succeeded"] == 0
    assert second.json()["summary"]["failed"] == 1
    # message should explain already housed / not require / conflict
    msg = second.json()["rows"][0]["message"] or ""
    assert msg

    acc = await client.get(f"/api/v1/employees/{emp['id']}/accommodation", headers=admin)
    assert acc.status_code == 200
    assert acc.json()["status"] == "active"
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    flags = _bed_flags(beds, dorm["beds"][0]["bed_no"])
    assert flags["occupied"] is True
    assert flags["available"] is False


@pytest.mark.asyncio
async def test_ux004_two_batches_race_same_bed(client: AsyncClient):
    """Concurrent batches targeting one bed: exactly one occupancy."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp_a = await make_employee(client, admin, suffix="争A")
    emp_b = await make_employee(client, admin, suffix="争B")
    content_a = await _alloc_payload(client, admin, emp_a, dorm)
    content_b = await _alloc_payload(client, admin, emp_b, dorm)

    r1, r2 = await asyncio.gather(
        _post_alloc(client, admin, content_a),
        _post_alloc(client, admin, content_b),
    )
    assert r1.status_code == 200 and r2.status_code == 200
    s1 = r1.json()["summary"]["succeeded"]
    s2 = r2.json()["summary"]["succeeded"]
    assert s1 + s2 == 1, f"double occupancy? {s1}+{s2}"

    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    flags = _bed_flags(beds, dorm["beds"][0]["bed_no"])
    assert flags["occupied"] is True
    assert flags["available"] is False


@pytest.mark.asyncio
async def test_ux004_no_modify_foreign_active_reservation(client: AsyncClient):
    """Batch failure recovery must not cancel another employee's active reservation."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    # employee A already has an active reservation via normal flow
    emp_a = await make_employee(client, admin, suffix="他人预留")
    app = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=admin,
            json={"employee_id": emp_a["id"], "application_type": "new"},
        )
    ).json()
    await client.post(f"/api/v1/checkin-applications/{app['id']}/approve", headers=admin, json={})
    await client.post(
        f"/api/v1/checkin-applications/{app['id']}/reserve",
        headers=admin,
        json={"bed_id": dorm["beds"][0]["id"]},
    )

    emp_b = await make_employee(client, admin, suffix="批失败B")
    content = await _alloc_payload(client, admin, emp_b, dorm, bed_no=dorm["beds"][1]["bed_no"])

    orig_confirm = checkin_service.confirm_checkin
    orig_cancel = checkin_service.cancel_application

    async def boom(*args, **kwargs):
        raise RuntimeError("injected")

    monkeypatch_ok = True
    # fail confirm and cancel for the batch row only via counter
    state = {"n": 0}

    async def fail_second(*args, **kwargs):
        state["n"] += 1
        raise RuntimeError("injected")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(checkin_service, "confirm_checkin", fail_second)
    monkeypatch.setattr(checkin_service, "cancel_application", fail_second)
    try:
        resp = await _post_alloc(client, admin, content)
    finally:
        monkeypatch.undo()

    assert resp.status_code == 200
    row = resp.json()["rows"][0]
    assert row["action"] == "error"

    # foreign reservation for emp_a must remain active
    state_a = await client.get(f"/api/v1/checkin-applications/{app['id']}", headers=admin)
    assert state_a.status_code == 200
    assert state_a.json()["status"] in {"reserved", "checked_in"}
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert _bed_flags(beds, dorm["beds"][0]["bed_no"])["reserved"] is True


# ========== FEAT-008 global rotation authorization ==========


@pytest.mark.asyncio
async def test_feat008_rotate_allowed_for_super_admin(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    await client.put(
        f"/api/v1/rooms/{dorm['room']['id']}/access-code",
        headers=admin,
        json={"access_code": "001122"},
    )
    rot = await client.post("/api/v1/rooms/access-code/rotate", headers=admin, json={})
    assert rot.status_code == 200, rot.text
    assert "001122" not in rot.text
    reveal = await client.get(
        f"/api/v1/rooms/{dorm['room']['id']}/access-code", headers=admin
    )
    assert reveal.json()["access_code"] == "001122"


@pytest.mark.asyncio
async def test_feat008_rotate_forbidden_for_dorm_admin_hr_finance_dept(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    await client.put(
        f"/api/v1/rooms/{dorm['room']['id']}/access-code",
        headers=admin,
        json={"access_code": "rotate-me"},
    )
    for role, prefix in [
        ("dorm_admin", "da"),
        ("hr", "hr"),
        ("finance_viewer", "fv"),
        ("dept_manager", "dm"),
    ]:
        user = await make_user_with_role(client, admin, role, f"rot{prefix}")
        headers = await headers_for_user(client, user["username"])
        resp = await client.post("/api/v1/rooms/access-code/rotate", headers=headers, json={})
        assert resp.status_code == 403, f"{role} should not rotate: {resp.text}"
        assert "rotate-me" not in resp.text


@pytest.mark.asyncio
async def test_feat008_dorm_admin_can_still_manage_room_codes(client: AsyncClient):
    """Per-room code maintenance stays available to dorm_admin."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    room_id = dorm["room"]["id"]
    user = await make_user_with_role(client, admin, "dorm_admin", "dacode")
    headers = await headers_for_user(client, user["username"])

    set_r = await client.put(
        f"/api/v1/rooms/{room_id}/access-code",
        headers=headers,
        json={"access_code": "008800"},
    )
    assert set_r.status_code == 200, set_r.text
    reveal = await client.get(f"/api/v1/rooms/{room_id}/access-code", headers=headers)
    assert reveal.json()["access_code"] == "008800"


@pytest.mark.asyncio
async def test_feat008_rotate_allowed_for_secrets_ops_role(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    await client.put(
        f"/api/v1/rooms/{dorm['room']['id']}/access-code",
        headers=admin,
        json={"access_code": "004455"},
    )
    user = await make_user_with_role(client, admin, "secrets_ops", "sops")
    headers = await headers_for_user(client, user["username"])
    rot = await client.post("/api/v1/rooms/access-code/rotate", headers=headers, json={})
    assert rot.status_code == 200, rot.text
    # secrets_ops can rotate but the room code still readable by authorized viewer
    reveal = await client.get(
        f"/api/v1/rooms/{dorm['room']['id']}/access-code", headers=admin
    )
    assert reveal.json()["access_code"] == "004455"


@pytest.mark.asyncio
async def test_feat008_rotate_failure_does_not_corrupt_ciphertext(
    client: AsyncClient, monkeypatch
):
    """If re-encrypt throws, the stored ciphertext must remain decryptable."""
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    room_id = dorm["room"]["id"]
    await client.put(
        f"/api/v1/rooms/{room_id}/access-code",
        headers=admin,
        json={"access_code": "009911"},
    )

    # Force a legacy-format token so rotate actually attempts re-encryption.
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.core.security import decrypt_access_code
    from app.models.dorm import DormRoom

    async with AsyncSessionLocal() as db:
        room = (
            await db.execute(select(DormRoom).where(DormRoom.id == room_id))
        ).scalar_one()
        plain = decrypt_access_code(room.access_code_encrypted)
        assert plain == "009911"
        # rewrite as bare Fernet token (needs_reencrypt == True)
        from app.core import security as security_mod

        room.access_code_encrypted = (
            security_mod._fernet_from_material(
                security_mod._access_code_primary_material()
            )
            .encrypt(plain.encode())
            .decode()
        )
        await db.commit()

    from app.core import security as security_mod

    def boom(token: str) -> str:
        raise RuntimeError("injected reencrypt failure")

    monkeypatch.setattr(security_mod, "reencrypt_access_code_token", boom)
    # migrate imports reencrypt inside the function — patch the source symbol
    rot = await client.post("/api/v1/rooms/access-code/rotate", headers=admin, json={})
    monkeypatch.undo()

    assert rot.status_code == 200, rot.text
    assert rot.json()["failed"] >= 1
    # original ciphertext still decryptable — rotate must not destroy it
    reveal = await client.get(f"/api/v1/rooms/{room_id}/access-code", headers=admin)
    assert reveal.status_code == 200
    assert reveal.json()["access_code"] == "009911"
