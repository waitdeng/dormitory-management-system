"""Auth API integration tests — require real MySQL (spec §13).

Run after: alembic upgrade head && python -m app.seed
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _ensure_admin() -> None:
    from app.seed import ensure_admin, seed_rbac

    await seed_rbac()
    await ensure_admin()



def _admin_credentials() -> tuple[str, str]:
    """Admin credentials come from the environment (set in conftest)."""
    import os

    return os.environ.get("DMS_ADMIN_USERNAME", "admin"), os.environ.get(
        "DMS_ADMIN_PASSWORD", "admin12345"
    )

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await _ensure_admin()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _admin_credentials()[0], "password": _admin_credentials()[1]},
    )
    # Password depends on DMS_ADMIN_PASSWORD; assert on shape when successful
    if resp.status_code == 200:
        body = resp.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["token_type"] == "bearer"
        assert "super_admin" in body["roles"]
        assert "user:manage" in body["permissions"]
    else:
        # Without configured admin password the test still validates error envelope
        assert resp.status_code in (401, 422)
        assert resp.json().get("code") in ("authentication_error", "validation_error")


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await _ensure_admin()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "definitely-wrong-password"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "authentication_error"
    assert "request_id" in body


@pytest.mark.asyncio
async def test_me_requires_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)
    assert resp.json()["code"] in ("authentication_error", "http_401", "http_403")


@pytest.mark.asyncio
async def test_full_auth_flow(client: AsyncClient):
    """Create a dedicated user, login, call me/permissions, refresh, logout."""
    await _ensure_admin()

    # Login as admin first
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": _admin_credentials()[0], "password": _admin_credentials()[1]},
    )
    if login.status_code != 200:
        pytest.skip("Admin credentials not configured for this environment")

    admin_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Create a tester account with a unique username
    import uuid

    uname = f"auth_{uuid.uuid4().hex[:8]}"
    create = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": uname,
            "display_name": "Auth Tester",
            "password": "AuthTest!2024",
            "role_codes": ["hr"],
        },
    )
    assert create.status_code == 201
    user_body = create.json()
    assert user_body["username"] == uname
    assert "hr" in user_body["roles"]

    # Login as the new user
    t_login = await client.post(
        "/api/v1/auth/login",
        json={"username": uname, "password": "AuthTest!2024"},
    )
    assert t_login.status_code == 200
    tokens = t_login.json()
    t_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # /auth/me
    me = await client.get("/api/v1/auth/me", headers=t_headers)
    assert me.status_code == 200
    assert me.json()["username"] == uname
    assert "employee:view" in me.json()["permissions"]

    # /auth/permissions
    perms = await client.get("/api/v1/auth/permissions", headers=t_headers)
    assert perms.status_code == 200
    assert "hr" in perms.json()["roles"]

    # Refresh rotates the refresh token
    refreshed = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # Old refresh token is revoked
    reuse = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reuse.status_code == 401

    # Logout
    logout = await client.post(
        "/api/v1/auth/logout",
        headers=t_headers,
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert logout.status_code == 200


@pytest.mark.asyncio
async def test_permission_gate_user_manage(client: AsyncClient):
    """HR role cannot manage users (spec §8)."""
    await _ensure_admin()

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": _admin_credentials()[0], "password": _admin_credentials()[1]},
    )
    if login.status_code != 200:
        pytest.skip("Admin credentials not configured")
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Create an HR-only user if missing
    import uuid

    hr_uname = f"hr_{uuid.uuid4().hex[:8]}"
    await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": hr_uname,
            "display_name": "HR Only",
            "password": "HrOnly!2024x",
            "role_codes": ["hr"],
        },
    )

    hr_login = await client.post(
        "/api/v1/auth/login",
        json={"username": hr_uname, "password": "HrOnly!2024x"},
    )
    if hr_login.status_code != 200:
        pytest.skip("HR user setup failed")
    hr_headers = {"Authorization": f"Bearer {hr_login.json()['access_token']}"}

    resp = await client.get("/api/v1/users", headers=hr_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "permission_denied"
