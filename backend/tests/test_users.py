"""User management API integration tests — require real MySQL."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _admin_headers(client: AsyncClient) -> dict[str, str] | None:
    from app.seed import ensure_admin, seed_rbac

    await seed_rbac()
    await ensure_admin()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": _admin_credentials()[0], "password": _admin_credentials()[1]},
    )
    if login.status_code != 200:
        return None
    return {"Authorization": f"Bearer {login.json()['access_token']}"}



def _admin_credentials() -> tuple[str, str]:
    """Admin credentials come from the environment (set in conftest)."""
    import os

    return os.environ.get("DMS_ADMIN_USERNAME", "admin"), os.environ.get(
        "DMS_ADMIN_PASSWORD", "admin12345"
    )

@pytest.mark.asyncio
async def test_list_roles_and_permissions(client: AsyncClient):
    headers = await _admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    roles = await client.get("/api/v1/roles", headers=headers)
    assert roles.status_code == 200
    codes = [r["code"] for r in roles.json()]
    assert "super_admin" in codes
    assert "hr" in codes
    assert "dorm_admin" in codes

    perms = await client.get("/api/v1/permissions", headers=headers)
    assert perms.status_code == 200
    perm_codes = [p["code"] for p in perms.json()]
    assert "employee:view" in perm_codes
    assert "user:manage" in perm_codes


@pytest.mark.asyncio
async def test_user_crud_and_roles(client: AsyncClient):
    headers = await _admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    import uuid

    uname = f"crud_{uuid.uuid4().hex[:8]}"
    create_payload = {
        "username": uname,
        "display_name": "CRUD User",
        "password": "CrudUser!2024",
        "role_codes": ["finance_viewer"],
    }
    first = await client.post("/api/v1/users", headers=headers, json=create_payload)
    assert first.status_code == 201
    user_id = first.json()["id"]
    assert first.json()["roles"] == ["finance_viewer"]

    # Update display name
    upd = await client.patch(
        f"/api/v1/users/{user_id}",
        headers=headers,
        json={"display_name": "CRUD Renamed"},
    )
    assert upd.status_code == 200
    assert upd.json()["display_name"] == "CRUD Renamed"

    # Replace roles
    roles = await client.put(
        f"/api/v1/users/{user_id}/roles",
        headers=headers,
        json={"role_codes": ["dept_manager"]},
    )
    assert roles.status_code == 200
    assert roles.json()["roles"] == ["dept_manager"]

    # List contains the user
    listing = await client.get(
        "/api/v1/users",
        headers=headers,
        params={"keyword": uname},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1

    # Unknown role → 400/422
    bad = await client.put(
        f"/api/v1/users/{user_id}/roles",
        headers=headers,
        json={"role_codes": ["no_such_role"]},
    )
    assert bad.status_code in (400, 422)


@pytest.mark.asyncio
async def test_disable_account_revokes_login(client: AsyncClient):
    headers = await _admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    import uuid

    uname = f"disable_me_{uuid.uuid4().hex[:8]}"
    create = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": uname,
            "display_name": "Disable Me",
            "password": "DisableMe!2024",
            "role_codes": [],
        },
    )
    assert create.status_code == 201
    user_id = create.json()["id"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": uname, "password": "DisableMe!2024"},
    )
    assert login.status_code == 200

    disable = await client.patch(
        f"/api/v1/users/{user_id}",
        headers=headers,
        json={"status": "disabled"},
    )
    assert disable.status_code == 200

    again = await client.post(
        "/api/v1/auth/login",
        json={"username": uname, "password": "DisableMe!2024"},
    )
    assert again.status_code == 401
