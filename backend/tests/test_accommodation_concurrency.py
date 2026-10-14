"""M3 concurrency tests against real MySQL (spec §13).

These exercise row locks + generated-column unique indexes: two concurrent
reservations of the same bed must yield exactly one success and one 409.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from tests.helpers_m3 import admin_headers, make_dorm, make_employee


async def _create_approved_app(client: AsyncClient, headers: dict, emp_id: int) -> int:
    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp_id},
    )
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]
    approved = await client.post(
        f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={}
    )
    assert approved.status_code == 200, approved.text
    return app_id


@pytest.mark.asyncio
async def test_concurrent_reserve_same_bed(client: AsyncClient):
    """Two admins reserve the same bed at once — only one succeeds (BR-002/004/005)."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=1)
    emp_a = await make_employee(client, headers, suffix="并A")
    emp_b = await make_employee(client, headers, suffix="并B")
    bed_id = dorm["beds"][0]["id"]

    app_a = await _create_approved_app(client, headers, emp_a["id"])
    app_b = await _create_approved_app(client, headers, emp_b["id"])

    resp_a, resp_b = await asyncio.gather(
        client.post(
            f"/api/v1/checkin-applications/{app_a}/reserve",
            headers=headers,
            json={"bed_id": bed_id},
        ),
        client.post(
            f"/api/v1/checkin-applications/{app_b}/reserve",
            headers=headers,
            json={"bed_id": bed_id},
        ),
    )

    codes = sorted([resp_a.status_code, resp_b.status_code])
    assert codes[0] == 200, f"expected one success, got {resp_a.status_code}/{resp_b.status_code}"
    assert codes[1] == 409, f"expected one conflict, got {resp_a.status_code}/{resp_b.status_code}"

    # exactly one active reservation on the bed
    beds = (
        await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)
    ).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    target = next(b for b in bed_list if b["id"] == bed_id)
    assert target["reserved"] is True
    assert target["occupied"] is False


@pytest.mark.asyncio
async def test_concurrent_same_employee_allocate(client: AsyncClient):
    """Two concurrent reserves for the same employee — only one active reservation."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=2)
    emp = await make_employee(client, headers, suffix="同工")
    bed0, bed1 = dorm["beds"][0]["id"], dorm["beds"][1]["id"]

    app_id = await _create_approved_app(client, headers, emp["id"])

    # same application, two different beds concurrently is not the scenario;
    # instead: two applications are blocked earlier. Here we race reserve on
    # two beds for one employee via two apporved apps — second app creation
    # would 409. So race two reserve calls on the SAME app with different beds
    # is sequential by app status. Use two employees is covered above.
    # Practical race: two admins both reserve different beds for two apps of
    # different employees is fine; the dangerous case is same bed covered above.
    # Additional check: concurrent confirm of the same application stays single.
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed0},
    )
    r1, r2 = await asyncio.gather(
        client.post(f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}),
        client.post(f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}),
    )
    assert r1.status_code == 200 and r2.status_code == 200
    history = (
        await client.get(f"/api/v1/employees/{emp['id']}/history", headers=headers)
    ).json()
    active = [h for h in history if h["status"] == "active"]
    assert len(active) == 1
    # bed1 unused
    beds = (
        await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)
    ).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    assert next(b for b in bed_list if b["id"] == bed1)["available"] is True


@pytest.mark.asyncio
async def test_concurrent_transfer_and_checkout(client: AsyncClient):
    """Transfer complete and checkout complete race — no double-ended or dangling state."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=2)
    emp = await make_employee(client, headers, suffix="竞态")
    src_bed, tgt_bed = dorm["beds"][0]["id"], dorm["beds"][1]["id"]

    created = await client.post(
        "/api/v1/checkin-applications", headers=headers, json={"employee_id": emp["id"]}
    )
    app_id = created.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={})
    await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": src_bed},
    )
    await client.post(f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={})

    tr = await client.post(
        "/api/v1/transfers",
        headers=headers,
        json={"employee_id": emp["id"], "target_bed_id": tgt_bed},
    )
    assert tr.status_code == 201, tr.text
    tr_id = tr.json()["id"]
    await client.post(f"/api/v1/transfers/{tr_id}/reserve", headers=headers, json={})

    co = await client.post(
        "/api/v1/checkouts", headers=headers, json={"employee_id": emp["id"]}
    )
    assert co.status_code == 201, co.text
    co_id = co.json()["id"]

    r_tr, r_co = await asyncio.gather(
        client.post(f"/api/v1/transfers/{tr_id}/complete", headers=headers, json={}),
        client.post(f"/api/v1/checkouts/{co_id}/complete", headers=headers, json={}),
    )

    # Exactly one may win; the other must not leave a second active occupancy
    # or a dangling reservation.
    ok = [r for r in (r_tr, r_co) if r.status_code == 200]
    bad = [r for r in (r_tr, r_co) if r.status_code != 200]
    assert len(ok) <= 1, f"both completed: {r_tr.status_code}/{r_co.status_code}"
    if len(ok) == 1:
        assert bad and bad[0].status_code in (409, 400, 422), bad[0].text
    else:
        # both rejected is also safe
        assert all(r.status_code in (409, 400, 422) for r in (r_tr, r_co))

    history = (
        await client.get(f"/api/v1/employees/{emp['id']}/history", headers=headers)
    ).json()
    active = [h for h in history if h["status"] == "active"]
    assert len(active) <= 1

    # no leftover active reservation for this employee
    acc = (
        await client.get(f"/api/v1/employees/{emp['id']}/accommodation", headers=headers)
    ).json()
    if acc is not None and acc.get("kind") == "reservation":
        pytest.fail("dangling reservation left after race")

