"""M4 P0 mandatory scenarios A–F: offboarding / termination vs checkout.

Scenario map (user instruction):
  A employee enters offboarding  → admin checkout to-do, bed still occupied
  B employee terminated not checked out → alert, bed still occupied
  C repeated offboarding/termination events → idempotent
  D admin confirms checkout → ended history, bed free, to-do + alert closed
  E duplicate checkout confirm → idempotent
  F concurrency + permission isolation

These tests run against real MySQL 8.0 (spec §13 / AGENTS.md §8).
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from tests.helpers_m4 import (
    admin_headers,
    checkin_employee,
    headers_for_user,
    make_dorm,
    make_employee,
    make_user_with_role,
)


async def _setup_housed_employee(
    client: AsyncClient, headers: dict, suffix: str
) -> tuple[dict, int, int]:
    """Create dorm + employee + check-in. Returns (emp, bed_id, room_id)."""
    dorm = await make_dorm(client, headers, capacity=2)
    emp = await make_employee(client, headers, suffix=suffix)
    bed_id = dorm["beds"][0]["id"]
    await checkin_employee(client, headers, emp["id"], bed_id)
    return emp, bed_id, dorm["room"]["id"]


async def _bed_flags(client: AsyncClient, headers: dict, room_id: int, bed_id: int) -> dict:
    beds = (await client.get(f"/api/v1/rooms/{room_id}/beds", headers=headers)).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    return next(b for b in bed_list if b["id"] == bed_id)


async def _active_accommodations(client: AsyncClient, headers: dict, emp_id: int) -> list:
    history = (
        await client.get(f"/api/v1/employees/{emp_id}/history", headers=headers)
    ).json()
    return [h for h in history if h["status"] == "active"]


async def _pending_checkout_todos(client: AsyncClient, headers: dict, emp_id: int) -> list:
    todos = (
        await client.get(
            "/api/v1/workflow/todos",
            headers=headers,
            params={"status": "pending", "employee_id": emp_id},
        )
    ).json()
    return [t for t in todos["items"] if t["todo_type"] == "checkout_offboarding"]


async def _active_alerts(
    client: AsyncClient, headers: dict, emp_id: int, alert_type: str
) -> list:
    alerts = (
        await client.get(
            "/api/v1/workflow/alerts",
            headers=headers,
            params={"status": "active", "employee_id": emp_id, "alert_type": alert_type},
        )
    ).json()
    return alerts["items"]


@pytest.mark.asyncio
async def test_p0_a_offboarding_creates_checkout_todo_keeps_bed(client: AsyncClient):
    """P0 A: offboarding generates admin checkout to-do; bed stays occupied."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    emp, bed_id, room_id = await _setup_housed_employee(client, headers, "P0A")
    emp_id = emp["id"]

    resp = await client.post(
        f"/api/v1/employees/{emp_id}/offboarding",
        headers=headers,
        json={"reason": "个人原因离职"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["employment_status"] == "offboarding"
    assert body["event"] is not None
    assert body["event"]["event_type"] == "offboarding"
    assert body["side_effects"]["todo_id"] is not None
    assert body["side_effects"]["checkout_id"] is not None

    # exactly one pending checkout to-do
    todos = await _pending_checkout_todos(client, headers, emp_id)
    assert len(todos) == 1, todos
    assert todos[0]["status"] == "pending"
    assert todos[0]["business_type"] == "checkout"

    # bed still occupied, accommodation still active
    flags = await _bed_flags(client, headers, room_id, bed_id)
    assert flags["occupied"] is True
    assert flags["available"] is False

    active = await _active_accommodations(client, headers, emp_id)
    assert len(active) == 1
    assert active[0]["bed_id"] == bed_id

    # another employee cannot take the bed
    other = await make_employee(client, headers, suffix="P0A抢床")
    app = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": other["id"]},
    )
    app_id = app.json()["id"]
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={}
    )
    reserve = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id},
    )
    assert reserve.status_code == 409, reserve.text

    # PATCH status path also works for a second employee (route check)
    emp2 = await make_employee(client, headers, suffix="P0A补")
    dorm2 = await make_dorm(client, headers)
    await checkin_employee(client, headers, emp2["id"], dorm2["beds"][0]["id"])
    patch = await client.patch(
        f"/api/v1/employees/{emp2['id']}",
        headers=headers,
        json={"employment_status": "offboarding"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["employment_status"] == "offboarding"
    todos2 = await _pending_checkout_todos(client, headers, emp2["id"])
    assert len(todos2) == 1


@pytest.mark.asyncio
async def test_p0_b_terminated_still_housed_alert(client: AsyncClient):
    """P0 B: termination keeps occupancy and raises 离职未退宿 alert."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    emp, bed_id, room_id = await _setup_housed_employee(client, headers, "P0B")
    emp_id = emp["id"]

    await client.post(
        f"/api/v1/employees/{emp_id}/offboarding", headers=headers, json={}
    )
    resp = await client.post(
        f"/api/v1/employees/{emp_id}/terminate",
        headers=headers,
        json={"reason": "离职手续办结"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["employment_status"] == "terminated"

    # still housed
    active = await _active_accommodations(client, headers, emp_id)
    assert len(active) == 1
    flags = await _bed_flags(client, headers, room_id, bed_id)
    assert flags["occupied"] is True

    # alert present
    alerts = await _active_alerts(client, headers, emp_id, "terminated_still_housed")
    assert len(alerts) == 1, alerts
    assert alerts[0]["severity"] == "critical"

    # checkout to-do still pending
    todos = await _pending_checkout_todos(client, headers, emp_id)
    assert len(todos) == 1
    assert todos[0]["status"] == "pending"

    # system must not auto-release
    emp_after = (await client.get(f"/api/v1/employees/{emp_id}", headers=headers)).json()
    assert emp_after["accommodation_status"] == "in_dorm"


@pytest.mark.asyncio
async def test_p0_c_repeated_events_idempotent(client: AsyncClient):
    """P0 C: repeated offboarding/terminate does not duplicate side-effects."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    emp, bed_id, room_id = await _setup_housed_employee(client, headers, "P0C")
    emp_id = emp["id"]

    r1 = await client.post(
        f"/api/v1/employees/{emp_id}/offboarding", headers=headers, json={}
    )
    assert r1.status_code == 200
    r2 = await client.post(
        f"/api/v1/employees/{emp_id}/offboarding", headers=headers, json={}
    )
    assert r2.status_code == 200
    assert r2.json()["event_created"] is False

    t1 = await client.post(
        f"/api/v1/employees/{emp_id}/terminate", headers=headers, json={}
    )
    assert t1.status_code == 200
    t2 = await client.post(
        f"/api/v1/employees/{emp_id}/terminate", headers=headers, json={}
    )
    assert t2.status_code == 200
    assert t2.json()["event_created"] is False

    # also with explicit same idempotency_key
    t3 = await client.post(
        f"/api/v1/employees/{emp_id}/terminate",
        headers=headers,
        json={"idempotency_key": "same-key-1"},
    )
    assert t3.status_code == 200
    t4 = await client.post(
        f"/api/v1/employees/{emp_id}/terminate",
        headers=headers,
        json={"idempotency_key": "same-key-1"},
    )
    assert t4.status_code == 200
    assert t4.json()["event_created"] is False

    todos = await _pending_checkout_todos(client, headers, emp_id)
    assert len(todos) == 1, todos

    alerts = await _active_alerts(client, headers, emp_id, "terminated_still_housed")
    assert len(alerts) == 1, alerts

    active = await _active_accommodations(client, headers, emp_id)
    assert len(active) == 1
    flags = await _bed_flags(client, headers, room_id, bed_id)
    assert flags["occupied"] is True

    # status events are recorded but not exploded by repeats of the same key
    events = (
        await client.get(f"/api/v1/employees/{emp_id}/status-events", headers=headers)
    ).json()["items"]
    # at least offboarding + terminate (+ one unique same-key-1)
    assert len(events) >= 2
    # no duplicate source_event_id
    keys = [(e["source"], e["source_event_id"]) for e in events]
    assert len(keys) == len(set(keys))


@pytest.mark.asyncio
async def test_p0_d_admin_checkout_closes_todo_and_alert(client: AsyncClient):
    """P0 D: completing checkout ends occupancy, frees bed, closes todo+alert."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    emp, bed_id, room_id = await _setup_housed_employee(client, headers, "P0D")
    emp_id = emp["id"]

    await client.post(f"/api/v1/employees/{emp_id}/offboarding", headers=headers, json={})
    await client.post(f"/api/v1/employees/{emp_id}/terminate", headers=headers, json={})

    # find the open checkout
    cos = (
        await client.get(
            "/api/v1/checkouts", headers=headers, params={"employee_id": emp_id}
        )
    ).json()
    open_cos = [c for c in cos["items"] if c["status"] in ("pending", "inspection")]
    assert len(open_cos) == 1
    co_id = open_cos[0]["id"]

    # inspection then complete (admin does the physical checkout)
    insp = await client.patch(
        f"/api/v1/checkouts/{co_id}/inspection",
        headers=headers,
        json={
            "key_returned": True,
            "access_card_returned": True,
            "belongings_cleared": True,
            "room_inspected": True,
        },
    )
    assert insp.status_code == 200, insp.text

    done = await client.post(
        f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={}
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"

    # accommodation ended, history preserved
    history = (
        await client.get(f"/api/v1/employees/{emp_id}/history", headers=headers)
    ).json()
    assert len(history) == 1
    assert history[0]["status"] == "ended"
    assert history[0]["bed_id"] == bed_id
    assert history[0]["checkout_at"] is not None

    # bed free
    flags = await _bed_flags(client, headers, room_id, bed_id)
    assert flags["occupied"] is False
    assert flags["available"] is True

    # todo auto-closed
    todos = await _pending_checkout_todos(client, headers, emp_id)
    assert len(todos) == 0
    all_todos = (
        await client.get(
            "/api/v1/workflow/todos",
            headers=headers,
            params={"employee_id": emp_id},
        )
    ).json()["items"]
    closed = [t for t in all_todos if t["todo_type"] == "checkout_offboarding"]
    assert closed and all(t["status"] == "completed" for t in closed)

    # alert resolved
    alerts = await _active_alerts(client, headers, emp_id, "terminated_still_housed")
    assert len(alerts) == 0
    resolved = (
        await client.get(
            "/api/v1/workflow/alerts",
            headers=headers,
            params={"status": "resolved", "employee_id": emp_id},
        )
    ).json()["items"]
    assert any(a["alert_type"] == "terminated_still_housed" for a in resolved)

    # employment status unchanged (still terminated)
    emp_after = (await client.get(f"/api/v1/employees/{emp_id}", headers=headers)).json()
    assert emp_after["employment_status"] == "terminated"


@pytest.mark.asyncio
async def test_p0_e_duplicate_checkout_confirm_idempotent(client: AsyncClient):
    """P0 E: repeating complete returns the same result without new history."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    emp, bed_id, room_id = await _setup_housed_employee(client, headers, "P0E")
    emp_id = emp["id"]

    await client.post(f"/api/v1/employees/{emp_id}/offboarding", headers=headers, json={})
    await client.post(f"/api/v1/employees/{emp_id}/terminate", headers=headers, json={})

    cos = (
        await client.get(
            "/api/v1/checkouts", headers=headers, params={"employee_id": emp_id}
        )
    ).json()
    co_id = cos["items"][0]["id"]

    first = await client.post(
        f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={}
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={}
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "completed"
    assert second.json()["completed_at"] is not None
    assert first.json()["completed_at"] is not None

    history = (
        await client.get(f"/api/v1/employees/{emp_id}/history", headers=headers)
    ).json()
    assert len(history) == 1
    assert history[0]["status"] == "ended"

    # no second ended record, bed still free
    flags = await _bed_flags(client, headers, room_id, bed_id)
    assert flags["available"] is True

    # business audit for checkout.complete should not be duplicated by the
    # idempotent second call (second call short-circuits before audit write).
    # We only assert history uniqueness here; audit duplication is covered by
    # counting completed checkouts.
    cos_after = (
        await client.get(
            "/api/v1/checkouts", headers=headers, params={"employee_id": emp_id}
        )
    ).json()
    completed = [c for c in cos_after["items"] if c["status"] == "completed"]
    assert len(completed) == 1


@pytest.mark.asyncio
async def test_p0_f_permission_hr_cannot_checkout_admin_cannot_offboard(
    client: AsyncClient,
):
    """P0 F (permissions): HR cannot complete checkout; dorm admin cannot offboard."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    hr_user = await make_user_with_role(client, headers, "hr", "p0hr")
    admin_user = await make_user_with_role(client, headers, "dorm_admin", "p0da")
    hr_h = await headers_for_user(client, hr_user["username"])
    admin_h = await headers_for_user(client, admin_user["username"])

    emp, bed_id, room_id = await _setup_housed_employee(client, headers, "P0F")
    emp_id = emp["id"]

    # HR can start offboarding
    r = await client.post(
        f"/api/v1/employees/{emp_id}/offboarding", headers=hr_h, json={}
    )
    assert r.status_code == 200, r.text

    cos = (
        await client.get("/api/v1/checkouts", headers=headers, params={"employee_id": emp_id})
    ).json()
    co_id = cos["items"][0]["id"]

    # HR cannot complete checkout (no checkout:complete)
    denied = await client.post(
        f"/api/v1/checkouts/{co_id}/complete", headers=hr_h, json={}
    )
    assert denied.status_code == 403, denied.text

    # dorm admin cannot change employment status / offboard
    denied2 = await client.post(
        f"/api/v1/employees/{emp_id}/terminate", headers=admin_h, json={}
    )
    assert denied2.status_code == 403, denied2.text

    denied3 = await client.patch(
        f"/api/v1/employees/{emp_id}",
        headers=admin_h,
        json={"employment_status": "terminated"},
    )
    assert denied3.status_code == 403, denied3.text

    # super admin (admin_headers) can do both
    ok_off = await client.post(
        f"/api/v1/employees/{emp_id}/terminate", headers=headers, json={}
    )
    assert ok_off.status_code == 200, ok_off.text
    ok_co = await client.post(
        f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={}
    )
    assert ok_co.status_code == 200, ok_co.text

    # admin can complete checkout; state consistent
    flags = await _bed_flags(client, headers, room_id, bed_id)
    assert flags["available"] is True


@pytest.mark.asyncio
async def test_p0_f_concurrent_offboarding_and_checkout(client: AsyncClient):
    """P0 F: offboarding and checkout-complete race keeps data consistent."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    emp, bed_id, room_id = await _setup_housed_employee(client, headers, "P0F1")
    emp_id = emp["id"]

    # create a normal open checkout first so both sides race
    created = await client.post(
        "/api/v1/checkouts",
        headers=headers,
        json={"employee_id": emp_id, "checkout_type": "offboarding"},
    )
    assert created.status_code == 201, created.text
    co_id = created.json()["id"]

    r_off, r_co = await asyncio.gather(
        client.post(f"/api/v1/employees/{emp_id}/offboarding", headers=headers, json={}),
        client.post(f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={}),
    )

    # both may succeed in different orders, or one may 409; state must be sane
    assert r_off.status_code in (200, 409, 422), r_off.text
    assert r_co.status_code in (200, 409, 422), r_co.text

    active = await _active_accommodations(client, headers, emp_id)
    assert len(active) <= 1

    # no dangling occupancy if checkout completed
    history = (
        await client.get(f"/api/v1/employees/{emp_id}/history", headers=headers)
    ).json()
    ended = [h for h in history if h["status"] == "ended"]
    still = [h for h in history if h["status"] == "active"]
    if r_co.status_code == 200:
        assert len(still) == 0
        assert len(ended) == 1
        flags = await _bed_flags(client, headers, room_id, bed_id)
        assert flags["occupied"] is False

    # at most one pending checkout to-do
    todos = await _pending_checkout_todos(client, headers, emp_id)
    assert len(todos) <= 1


@pytest.mark.asyncio
async def test_p0_f_concurrent_duplicate_offboarding_events(client: AsyncClient):
    """P0 F: concurrent identical offboarding events stay idempotent."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    emp, bed_id, room_id = await _setup_housed_employee(client, headers, "P0F2")
    emp_id = emp["id"]
    race_key = f"race-{emp_id}"

    r1, r2 = await asyncio.gather(
        client.post(
            f"/api/v1/employees/{emp_id}/offboarding",
            headers=headers,
            json={"idempotency_key": race_key},
        ),
        client.post(
            f"/api/v1/employees/{emp_id}/offboarding",
            headers=headers,
            json={"idempotency_key": race_key},
        ),
    )
    assert r1.status_code in (200, 409), r1.text
    assert r2.status_code in (200, 409), r2.text
    # at least one success
    assert 200 in (r1.status_code, r2.status_code)

    todos = await _pending_checkout_todos(client, headers, emp_id)
    assert len(todos) == 1, todos

    active = await _active_accommodations(client, headers, emp_id)
    assert len(active) == 1
    flags = await _bed_flags(client, headers, room_id, bed_id)
    assert flags["occupied"] is True


@pytest.mark.asyncio
async def test_p0_f_concurrent_checkout_complete_and_alert_scan(client: AsyncClient):
    """P0 F: checkout complete racing alert scan leaves no stale alert."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    emp, bed_id, room_id = await _setup_housed_employee(client, headers, "P0F3")
    emp_id = emp["id"]
    await client.post(f"/api/v1/employees/{emp_id}/offboarding", headers=headers, json={})
    await client.post(f"/api/v1/employees/{emp_id}/terminate", headers=headers, json={})

    cos = (
        await client.get("/api/v1/checkouts", headers=headers, params={"employee_id": emp_id})
    ).json()
    co_id = cos["items"][0]["id"]

    r_co, r_scan = await asyncio.gather(
        client.post(f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={}),
        client.post("/api/v1/scanner/run", headers=headers),
    )
    assert r_co.status_code in (200, 409), r_co.text
    assert r_scan.status_code == 200, r_scan.text

    # after both finish, if checkout completed there must be no active
    # terminated_still_housed alert
    if r_co.status_code == 200:
        alerts = await _active_alerts(client, headers, emp_id, "terminated_still_housed")
        assert len(alerts) == 0, alerts
        flags = await _bed_flags(client, headers, room_id, bed_id)
        assert flags["occupied"] is False
