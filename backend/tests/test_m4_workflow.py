"""M4 specialty tests: reservation expiry scan + abnormal alerts (real MySQL)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.models.base import utcnow
from tests.helpers_m4 import (
    admin_headers,
    checkin_employee,
    make_dorm,
    make_employee,
)


async def _reserve_bed(
    client: AsyncClient,
    headers: dict,
    emp_id: int,
    bed_id: int,
    expires_at: str | None = None,
) -> dict:
    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp_id},
    )
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={}
    )
    payload: dict = {"bed_id": bed_id}
    if expires_at:
        payload["expires_at"] = expires_at
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json=payload,
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_reservation_expiry_releases_bed(client: AsyncClient):
    """Expired reservation is released; bed becomes available again."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="预留过期")
    bed_id = dorm["beds"][0]["id"]
    room_id = dorm["room"]["id"]

    past = (utcnow() - timedelta(hours=1)).isoformat()
    app = await _reserve_bed(client, headers, emp["id"], bed_id, expires_at=past)
    assert app["status"] == "reserved"
    assert app["reservation"]["status"] == "active"

    scan = await client.post("/api/v1/scanner/run", headers=headers)
    assert scan.status_code == 200, scan.text
    expired_ids = scan.json()["expiry"]["expired"]
    assert expired_ids, scan.json()

    beds = (await client.get(f"/api/v1/rooms/{room_id}/beds", headers=headers)).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    target = next(b for b in bed_list if b["id"] == bed_id)
    assert target["available"] is True
    assert target["reserved"] is False

    # reservation is no longer active (get_application only shows active)
    apps = (
        await client.get(
            "/api/v1/checkin-applications",
            headers=headers,
            params={"employee_id": emp["id"]},
        )
    ).json()
    detail = (
        await client.get(
            f"/api/v1/checkin-applications/{apps['items'][0]['id']}", headers=headers
        )
    ).json()
    assert detail.get("reservation") is None
    assert scan.json()["expiry"]["expired"]


@pytest.mark.asyncio
async def test_checked_in_bed_not_released_by_expiry_scan(client: AsyncClient):
    """A consumed reservation / live occupancy is never released by the scan."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="已入住")
    bed_id = dorm["beds"][0]["id"]
    room_id = dorm["room"]["id"]

    past = (utcnow() - timedelta(hours=1)).isoformat()
    # reserve with past expiry, then confirm check-in before scan
    created = await client.post(
        "/api/v1/checkin-applications", headers=headers, json={"employee_id": emp["id"]}
    )
    app_id = created.json()["id"]
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={}
    )
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id, "expires_at": past},
    )
    assert r.status_code == 200, r.text
    c = await client.post(
        f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
    )
    assert c.status_code == 200, c.text

    scan = await client.post("/api/v1/scanner/run", headers=headers)
    assert scan.status_code == 200, scan.text

    beds = (await client.get(f"/api/v1/rooms/{room_id}/beds", headers=headers)).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    target = next(b for b in bed_list if b["id"] == bed_id)
    assert target["occupied"] is True
    assert target["available"] is False

    history = (
        await client.get(f"/api/v1/employees/{emp['id']}/history", headers=headers)
    ).json()
    assert any(h["status"] == "active" for h in history)


@pytest.mark.asyncio
async def test_cancelled_reservation_not_expired_again(client: AsyncClient):
    """Cancelled reservations never produce another expiry event."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="已取消")
    bed_id = dorm["beds"][0]["id"]

    past = (utcnow() - timedelta(hours=1)).isoformat()
    app = await _reserve_bed(client, headers, emp["id"], bed_id, expires_at=past)
    app_id = app["id"]

    cancel = await client.post(
        f"/api/v1/checkin-applications/{app_id}/cancel",
        headers=headers,
        json={"reason": "不需要了"},
    )
    assert cancel.status_code == 200, cancel.text

    s1 = await client.post("/api/v1/scanner/run", headers=headers)
    assert s1.status_code == 200
    # the cancelled reservation must not be in expired list
    assert app_id not in s1.json()["expiry"].get("expired", [])
    res_id = app["reservation"]["id"]
    assert res_id not in s1.json()["expiry"].get("expired", [])

    s2 = await client.post("/api/v1/scanner/run", headers=headers)
    assert s2.status_code == 200
    assert res_id not in s2.json()["expiry"].get("expired", [])


@pytest.mark.asyncio
async def test_overdue_checkin_alert(client: AsyncClient):
    """Reserved application past requested_checkin_date raises overdue alert."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="超期未住")
    bed_id = dorm["beds"][0]["id"]

    past_date = (utcnow() - timedelta(days=3)).date().isoformat()
    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp["id"], "requested_checkin_date": past_date},
    )
    app_id = created.json()["id"]
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={}
    )
    # far-future expires_at so reservation is not expired by the scan
    future = (utcnow() + timedelta(days=7)).isoformat()
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id, "expires_at": future},
    )

    scan = await client.post("/api/v1/scanner/scan-alerts", headers=headers)
    assert scan.status_code == 200, scan.text

    alerts = (
        await client.get(
            "/api/v1/workflow/alerts",
            headers=headers,
            params={
                "status": "active",
                "alert_type": "overdue_checkin",
                "employee_id": emp["id"],
            },
        )
    ).json()
    assert len(alerts["items"]) >= 1

    # confirm check-in resolves the alert
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
    )
    alerts2 = (
        await client.get(
            "/api/v1/workflow/alerts",
            headers=headers,
            params={
                "status": "active",
                "alert_type": "overdue_checkin",
                "employee_id": emp["id"],
            },
        )
    ).json()
    assert alerts2["items"] == []


@pytest.mark.asyncio
async def test_completed_todo_not_listed_as_pending(client: AsyncClient):
    """After checkout completes, the todo is completed not pending."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="待办完成")
    bed_id = dorm["beds"][0]["id"]
    await checkin_employee(client, headers, emp["id"], bed_id)

    await client.post(f"/api/v1/employees/{emp['id']}/offboarding", headers=headers, json={})
    pending = (
        await client.get(
            "/api/v1/workflow/todos",
            headers=headers,
            params={"status": "pending", "employee_id": emp["id"]},
        )
    ).json()
    assert pending["total"] >= 1

    cos = (
        await client.get(
            "/api/v1/checkouts", headers=headers, params={"employee_id": emp["id"]}
        )
    ).json()
    co_id = cos["items"][0]["id"]
    done = await client.post(f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={})
    assert done.status_code == 200, done.text

    pending2 = (
        await client.get(
            "/api/v1/workflow/todos",
            headers=headers,
            params={"status": "pending", "employee_id": emp["id"]},
        )
    ).json()
    assert pending2["items"] == []

    summary = (await client.get("/api/v1/workflow/todos/summary", headers=headers)).json()
    assert summary["pending"] >= 0
    assert summary["completed"] >= 1


@pytest.mark.asyncio
async def test_repeated_scans_do_not_duplicate(client: AsyncClient):
    """Running the scanner twice creates no duplicate expirations or alerts."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=2)
    emp = await make_employee(client, headers, suffix="扫描重复")
    bed_id = dorm["beds"][0]["id"]

    past = (utcnow() - timedelta(hours=2)).isoformat()
    await _reserve_bed(client, headers, emp["id"], bed_id, expires_at=past)

    s1 = await client.post("/api/v1/scanner/run", headers=headers)
    assert s1.status_code == 200
    s2 = await client.post("/api/v1/scanner/run", headers=headers)
    assert s2.status_code == 200

    assert len(s1.json()["expiry"]["expired"]) >= 1
    assert s2.json()["expiry"]["expired"] == []

    # alert fingerprints unique among active rows
    alerts = (
        await client.get(
            "/api/v1/workflow/alerts",
            headers=headers,
            params={"status": "active"},
        )
    ).json()
    fps = [a["fingerprint"] for a in alerts["items"]]
    assert len(fps) == len(set(fps))


@pytest.mark.asyncio
async def test_scanner_safe_retry_after_partial_failure(client: AsyncClient):
    """Scanner is safe to re-run: already-expired rows are skipped."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=2)
    emp = await make_employee(client, headers, suffix="扫描重试")
    bed_id = dorm["beds"][0]["id"]
    past = (utcnow() - timedelta(hours=2)).isoformat()
    await _reserve_bed(client, headers, emp["id"], bed_id, expires_at=past)

    r1 = await client.post("/api/v1/scanner/expire-reservations", headers=headers)
    assert r1.status_code == 200
    r2 = await client.post("/api/v1/scanner/expire-reservations", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["expired"] == []
    assert r2.json()["scanned"] == 0 or r2.json()["expired"] == []


@pytest.mark.asyncio
async def test_offboarding_pending_checkouts_endpoint(client: AsyncClient):
    """GET /offboarding/pending-checkouts lists open offboarding checkouts."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="待退宿")
    await checkin_employee(client, headers, emp["id"], dorm["beds"][0]["id"])
    await client.post(f"/api/v1/employees/{emp['id']}/offboarding", headers=headers, json={})

    resp = await client.get("/api/v1/offboarding/pending-checkouts", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert any(i["employee_id"] == emp["id"] for i in items)


@pytest.mark.asyncio
async def test_todo_complete_and_alert_resolve_apis(client: AsyncClient):
    """Manual todo complete / alert resolve work and are idempotent."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="手动关闭")
    await checkin_employee(client, headers, emp["id"], dorm["beds"][0]["id"])
    await client.post(f"/api/v1/employees/{emp['id']}/offboarding", headers=headers, json={})
    await client.post(f"/api/v1/employees/{emp['id']}/terminate", headers=headers, json={})

    todos = (
        await client.get(
            "/api/v1/workflow/todos",
            headers=headers,
            params={"status": "pending", "employee_id": emp["id"]},
        )
    ).json()
    todo_id = todos["items"][0]["id"]
    r = await client.post(f"/api/v1/workflow/todos/{todo_id}/complete", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    r2 = await client.post(f"/api/v1/workflow/todos/{todo_id}/complete", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "completed"

    alerts = (
        await client.get(
            "/api/v1/workflow/alerts",
            headers=headers,
            params={"status": "active", "employee_id": emp["id"]},
        )
    ).json()
    assert alerts["items"]
    alert_id = alerts["items"][0]["id"]
    a = await client.post(f"/api/v1/workflow/alerts/{alert_id}/resolve", headers=headers)
    assert a.status_code == 200
    assert a.json()["status"] == "resolved"
    a2 = await client.post(f"/api/v1/workflow/alerts/{alert_id}/resolve", headers=headers)
    assert a2.status_code == 200
    assert a2.json()["status"] == "resolved"
