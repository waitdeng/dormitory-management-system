"""M3 accommodation transaction tests: check-in, transfer, checkout."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers_m3 import admin_headers, make_dorm, make_employee


async def _checkin_flow(client: AsyncClient, headers: dict, emp_id: int, bed_id: int) -> dict:
    """pending → approved → reserved → checked_in. Returns final application."""
    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp_id, "application_type": "new", "reason": "入职住宿"},
    )
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]

    approved = await client.post(
        f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    reserved = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id},
    )
    assert reserved.status_code == 200, reserved.text
    assert reserved.json()["status"] == "reserved"
    assert reserved.json()["assigned_bed_id"] == bed_id

    confirmed = await client.post(
        f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "checked_in"
    return confirmed.json()


@pytest.mark.asyncio
async def test_checkin_full_flow(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=2)
    emp = await make_employee(client, headers, suffix="入住")
    bed_id = dorm["beds"][0]["id"]

    await _checkin_flow(client, headers, emp["id"], bed_id)

    # employee accommodation status
    emp_after = (await client.get(f"/api/v1/employees/{emp['id']}", headers=headers)).json()
    assert emp_after["accommodation_status"] == "in_dorm"

    acc = (
        await client.get(f"/api/v1/employees/{emp['id']}/accommodation", headers=headers)
    ).json()
    assert acc is not None and acc["kind"] == "accommodation"
    assert acc["bed_id"] == bed_id

    history = (
        await client.get(f"/api/v1/employees/{emp['id']}/history", headers=headers)
    ).json()
    assert len(history) == 1
    assert history[0]["status"] == "active"

    # bed flags reflect occupancy
    beds = (
        await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)
    ).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    target = next(b for b in bed_list if b["id"] == bed_id)
    assert target["occupied"] is True
    assert target["available"] is False

    # active list
    active = (await client.get("/api/v1/accommodations/active", headers=headers)).json()
    assert any(r["employee_id"] == emp["id"] for r in active["items"])


@pytest.mark.asyncio
async def test_checkin_duplicate_confirm_idempotent(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers)
    emp = await make_employee(client, headers, suffix="幂等")
    bed_id = dorm["beds"][0]["id"]
    await _checkin_flow(client, headers, emp["id"], bed_id)

    # find the checked_in application and confirm again
    apps = (
        await client.get(
            "/api/v1/checkin-applications",
            headers=headers,
            params={"employee_id": emp["id"]},
        )
    ).json()
    app_id = apps["items"][0]["id"]

    again = await client.post(
        f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
    )
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "checked_in"

    # still only one active accommodation
    history = (
        await client.get(f"/api/v1/employees/{emp['id']}/history", headers=headers)
    ).json()
    active_count = sum(1 for h in history if h["status"] == "active")
    assert active_count == 1


@pytest.mark.asyncio
async def test_checkin_rejects_occupied_bed(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=1)
    emp1 = await make_employee(client, headers, suffix="甲")
    emp2 = await make_employee(client, headers, suffix="乙")
    bed_id = dorm["beds"][0]["id"]

    await _checkin_flow(client, headers, emp1["id"], bed_id)

    # second employee tries to reserve the same bed
    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp2["id"]},
    )
    assert created.status_code == 201
    app2 = created.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app2}/approve", headers=headers, json={})

    reserved = await client.post(
        f"/api/v1/checkin-applications/{app2}/reserve",
        headers=headers,
        json={"bed_id": bed_id},
    )
    assert reserved.status_code == 409, reserved.text


@pytest.mark.asyncio
async def test_checkin_rejects_employee_already_housed(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=2)
    emp = await make_employee(client, headers, suffix="重复")
    await _checkin_flow(client, headers, emp["id"], dorm["beds"][0]["id"])

    # new application for the same employee is rejected
    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp["id"]},
    )
    assert created.status_code == 409, created.text


@pytest.mark.asyncio
async def test_checkin_reserve_requires_approved(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers)
    emp = await make_employee(client, headers, suffix="未批")
    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp["id"]},
    )
    app_id = created.json()["id"]
    reserved = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": dorm["beds"][0]["id"]},
    )
    assert reserved.status_code == 409


@pytest.mark.asyncio
async def test_transfer_flow_keeps_history(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=2)
    emp = await make_employee(client, headers, suffix="调宿")
    src_bed = dorm["beds"][0]["id"]
    tgt_bed = dorm["beds"][1]["id"]
    await _checkin_flow(client, headers, emp["id"], src_bed)

    created = await client.post(
        "/api/v1/transfers",
        headers=headers,
        json={"employee_id": emp["id"], "target_bed_id": tgt_bed, "reason": "换床"},
    )
    assert created.status_code == 201, created.text
    tr_id = created.json()["id"]
    assert created.json()["status"] == "pending"

    reserved = await client.post(
        f"/api/v1/transfers/{tr_id}/reserve", headers=headers, json={}
    )
    assert reserved.status_code == 200, reserved.text
    assert reserved.json()["status"] == "reserved"

    completed = await client.post(
        f"/api/v1/transfers/{tr_id}/complete", headers=headers, json={}
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"

    history = (
        await client.get(f"/api/v1/employees/{emp['id']}/history", headers=headers)
    ).json()
    assert len(history) == 2
    statuses = {h["status"] for h in history}
    assert statuses == {"active", "ended"}
    ended = next(h for h in history if h["status"] == "ended")
    active = next(h for h in history if h["status"] == "active")
    assert ended["bed_id"] == src_bed
    assert ended["end_reason"] == "transfer"
    assert active["bed_id"] == tgt_bed

    # source bed is free again
    beds = (
        await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)
    ).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    src_view = next(b for b in bed_list if b["id"] == src_bed)
    assert src_view["occupied"] is False
    assert src_view["available"] is True


@pytest.mark.asyncio
async def test_transfer_target_conflict_rolls_back(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=2)
    emp_a = await make_employee(client, headers, suffix="调A")
    emp_b = await make_employee(client, headers, suffix="调B")
    bed0, bed1 = dorm["beds"][0]["id"], dorm["beds"][1]["id"]
    await _checkin_flow(client, headers, emp_a["id"], bed0)
    await _checkin_flow(client, headers, emp_b["id"], bed1)

    # A tries to transfer onto B's occupied bed
    created = await client.post(
        "/api/v1/transfers",
        headers=headers,
        json={"employee_id": emp_a["id"], "target_bed_id": bed1},
    )
    assert created.status_code == 201
    tr_id = created.json()["id"]
    reserved = await client.post(
        f"/api/v1/transfers/{tr_id}/reserve", headers=headers, json={}
    )
    assert reserved.status_code == 409, reserved.text

    # source accommodation unchanged
    acc = (
        await client.get(f"/api/v1/employees/{emp_a['id']}/accommodation", headers=headers)
    ).json()
    assert acc["bed_id"] == bed0
    assert acc["status"] == "active"


@pytest.mark.asyncio
async def test_transfer_same_bed_rejected(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers)
    emp = await make_employee(client, headers, suffix="同床")
    bed = dorm["beds"][0]["id"]
    await _checkin_flow(client, headers, emp["id"], bed)

    created = await client.post(
        "/api/v1/transfers",
        headers=headers,
        json={"employee_id": emp["id"], "target_bed_id": bed},
    )
    assert created.status_code == 400, created.text


@pytest.mark.asyncio
async def test_checkout_flow_frees_bed(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers)
    emp = await make_employee(client, headers, suffix="退宿")
    bed_id = dorm["beds"][0]["id"]
    await _checkin_flow(client, headers, emp["id"], bed_id)

    created = await client.post(
        "/api/v1/checkouts",
        headers=headers,
        json={"employee_id": emp["id"], "checkout_type": "normal", "reason": "合同结束"},
    )
    assert created.status_code == 201, created.text
    co_id = created.json()["id"]

    inspected = await client.patch(
        f"/api/v1/checkouts/{co_id}/inspection",
        headers=headers,
        json={
            "key_returned": True,
            "access_card_returned": True,
            "belongings_cleared": True,
            "room_inspected": True,
            "inspection_notes": "房间完好",
        },
    )
    assert inspected.status_code == 200, inspected.text
    assert inspected.json()["status"] == "inspection"

    completed = await client.post(
        f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={}
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"

    # employee no longer housed
    emp_after = (await client.get(f"/api/v1/employees/{emp['id']}", headers=headers)).json()
    assert emp_after["accommodation_status"] == "not_in_dorm"

    history = (
        await client.get(f"/api/v1/employees/{emp['id']}/history", headers=headers)
    ).json()
    assert history[0]["status"] == "ended"
    assert history[0]["checkout_at"] is not None

    # bed free again
    beds = (
        await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)
    ).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    target = next(b for b in bed_list if b["id"] == bed_id)
    assert target["available"] is True


@pytest.mark.asyncio
async def test_checkout_duplicate_open_rejected(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers)
    emp = await make_employee(client, headers, suffix="双退")
    await _checkin_flow(client, headers, emp["id"], dorm["beds"][0]["id"])

    first = await client.post(
        "/api/v1/checkouts",
        headers=headers,
        json={"employee_id": emp["id"]},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/checkouts",
        headers=headers,
        json={"employee_id": emp["id"]},
    )
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_checkout_complete_idempotent(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers)
    emp = await make_employee(client, headers, suffix="重退")
    await _checkin_flow(client, headers, emp["id"], dorm["beds"][0]["id"])
    created = await client.post(
        "/api/v1/checkouts", headers=headers, json={"employee_id": emp["id"]}
    )
    co_id = created.json()["id"]
    await client.post(f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={})

    again = await client.post(
        f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={}
    )
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "completed"

    history = (
        await client.get(f"/api/v1/employees/{emp['id']}/history", headers=headers)
    ).json()
    ended = [h for h in history if h["status"] == "ended"]
    assert len(ended) == 1


@pytest.mark.asyncio
async def test_cancel_releases_reservation(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers)
    emp = await make_employee(client, headers, suffix="取消")
    bed_id = dorm["beds"][0]["id"]

    created = await client.post(
        "/api/v1/checkin-applications", headers=headers, json={"employee_id": emp["id"]}
    )
    app_id = created.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={})
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id},
    )

    # bed shows reserved
    beds = (
        await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)
    ).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    assert next(b for b in bed_list if b["id"] == bed_id)["reserved"] is True

    cancelled = await client.post(
        f"/api/v1/checkin-applications/{app_id}/cancel",
        headers=headers,
        json={"reason": "员工放弃入住"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    beds2 = (
        await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)
    ).json()
    bed_list2 = beds2["items"] if isinstance(beds2, dict) else beds2
    assert next(b for b in bed_list2 if b["id"] == bed_id)["available"] is True


@pytest.mark.asyncio
async def test_disable_bed_with_occupancy_rejected(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers)
    emp = await make_employee(client, headers, suffix="停用")
    bed_id = dorm["beds"][0]["id"]
    await _checkin_flow(client, headers, emp["id"], bed_id)

    disabled = await client.post(
        f"/api/v1/beds/{bed_id}/disable", headers=headers, json={}
    )
    assert disabled.status_code == 409, disabled.text


@pytest.mark.asyncio
async def test_allocate_blocked_when_parent_disabled(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers)
    emp = await make_employee(client, headers, suffix="父停")
    bed_id = dorm["beds"][0]["id"]

    # disable room
    updated = await client.patch(
        f"/api/v1/rooms/{dorm['room']['id']}",
        headers=headers,
        json={"status": "disabled"},
    )
    assert updated.status_code == 200, updated.text

    created = await client.post(
        "/api/v1/checkin-applications", headers=headers, json={"employee_id": emp["id"]}
    )
    app_id = created.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={})
    reserved = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id},
    )
    assert reserved.status_code == 409, reserved.text


@pytest.mark.asyncio
async def test_permission_denied_for_checkin(client: AsyncClient):
    """finance_viewer has no checkin:create — 403."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    import uuid

    uname = f"fin_{uuid.uuid4().hex[:8]}"
    created = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": uname,
            "display_name": "Finance Viewer",
            "password": "Finance!2024",
            "role_codes": ["finance_viewer"],
        },
    )
    assert created.status_code == 201, created.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": uname, "password": "Finance!2024"},
    )
    assert login.status_code == 200, login.text
    limited = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post(
        "/api/v1/checkin-applications",
        headers=limited,
        json={"employee_id": 1},
    )
    assert resp.status_code == 403, resp.text
