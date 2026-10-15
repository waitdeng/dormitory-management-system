"""HOTFIX-05 BUG-014 — allocation candidate eligibility (real MySQL)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm, make_employee
from tests.helpers_m4 import checkin_employee


async def _mk_emp(client, headers, suffix: str, **overrides) -> dict:
    payload = {
        "employee_no": unique_code("E"),
        "full_name": f"候选{suffix}",
        "employment_status": "active",
        "accommodation_required": True,
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/employees", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _allocatable_ids(client, headers) -> set[int]:
    resp = await client.get(
        "/api/v1/employees",
        headers=headers,
        params={
            "page": 1,
            "page_size": 100,
            "accommodation_status": "allocatable",
            "employment_status": "active",
            "accommodation_required": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return {row["id"] for row in resp.json()["items"]}


@pytest.mark.asyncio
async def test_bug014_candidates_only_active_needing_housing(client: AsyncClient):
    admin = await admin_headers(client)
    ok = await _mk_emp(client, admin, "在职OK")
    for status in ("pending", "probation", "offboarding", "terminated", "resigned", "suspended"):
        await _mk_emp(client, admin, status, employment_status=status)
    await _mk_emp(client, admin, "不需住", accommodation_required=False)

    ids = await _allocatable_ids(client, admin)
    assert ok["id"] in ids
    # none of the non-active / no-housing employees appear
    listed = await client.get(
        "/api/v1/employees",
        headers=admin,
        params={"page": 1, "page_size": 100, "keyword": "候选"},
    )
    for row in listed.json()["items"]:
        if row["id"] == ok["id"]:
            continue
        if row["employment_status"] != "active" or not row["accommodation_required"]:
            assert row["id"] not in ids


@pytest.mark.asyncio
async def test_bug014_exclude_housed_and_reserved(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=3)
    housed = await _mk_emp(client, admin, "已入住")
    reserved = await _mk_emp(client, admin, "已预留")
    free = await _mk_emp(client, admin, "空闲")

    await checkin_employee(client, admin, housed["id"], dorm["beds"][0]["id"])

    app = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=admin,
            json={"employee_id": reserved["id"], "application_type": "new"},
        )
    ).json()
    await client.post(f"/api/v1/checkin-applications/{app['id']}/approve", headers=admin, json={})
    await client.post(
        f"/api/v1/checkin-applications/{app['id']}/reserve",
        headers=admin,
        json={"bed_id": dorm["beds"][1]["id"]},
    )

    ids = await _allocatable_ids(client, admin)
    assert free["id"] in ids
    assert housed["id"] not in ids
    assert reserved["id"] not in ids


@pytest.mark.asyncio
async def test_bug014_backend_blocks_non_active_allocation(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await _mk_emp(client, admin, "试用期", employment_status="probation")

    resp = await client.post(
        "/api/v1/checkin-applications",
        headers=admin,
        json={"employee_id": emp["id"], "application_type": "new"},
    )
    assert resp.status_code in (400, 409, 422), resp.text
    message = resp.json().get("message") or ""
    assert "active" in message or "eligible" in message or "在职" in message or "住宿" in message

    # reserve path also blocked if somehow an application existed
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=admin)).json()
    assert beds[0]["available"] is True


@pytest.mark.asyncio
async def test_bug014_search_scoped_to_candidates(client: AsyncClient):
    admin = await admin_headers(client)
    ok = await _mk_emp(client, admin, "搜索在职")
    bad = await _mk_emp(client, admin, "搜索停职", employment_status="suspended")

    resp = await client.get(
        "/api/v1/employees",
        headers=admin,
        params={
            "page": 1,
            "page_size": 50,
            "keyword": "搜索",
            "accommodation_status": "allocatable",
            "employment_status": "active",
            "accommodation_required": True,
        },
    )
    ids = {r["id"] for r in resp.json()["items"]}
    assert ok["id"] in ids
    assert bad["id"] not in ids
