"""M4 helpers: role users, check-in fixture, offboarding scenarios (real MySQL)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm, make_employee

__all__ = [
    "admin_headers",
    "unique_code",
    "make_dorm",
    "make_employee",
    "make_user_with_role",
    "headers_for_user",
    "checkin_employee",
    "create_open_checkout_for",
]


async def make_user_with_role(
    client: AsyncClient, headers: dict, role_code: str, prefix: str
) -> dict:
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": username,
            "display_name": f"{prefix}测试用户",
            "password": "TestPass12345",
            "role_codes": [role_code],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def headers_for_user(client: AsyncClient, username: str) -> dict[str, str]:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "TestPass12345"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def checkin_employee(
    client: AsyncClient, headers: dict, emp_id: int, bed_id: int
) -> dict:
    """Create application → approve → reserve → confirm. Returns application."""
    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp_id, "application_type": "new"},
    )
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={}
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def create_open_checkout_for(
    client: AsyncClient, headers: dict, emp_id: int
) -> dict:
    r = await client.post(
        "/api/v1/checkouts",
        headers=headers,
        json={"employee_id": emp_id, "checkout_type": "offboarding"},
    )
    assert r.status_code in (201, 409), r.text
    return r.json()
