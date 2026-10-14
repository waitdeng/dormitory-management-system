"""Shared helpers for M2 integration tests (real MySQL)."""

from __future__ import annotations

import os
import uuid

from httpx import AsyncClient


def _admin_credentials() -> tuple[str, str]:
    return (
        os.environ.get("DMS_ADMIN_USERNAME", "admin"),
        os.environ.get("DMS_ADMIN_PASSWORD", "admin12345"),
    )


async def admin_headers(client: AsyncClient) -> dict[str, str] | None:
    from app.seed import ensure_admin, seed_rbac

    await seed_rbac()
    await ensure_admin()
    username, password = _admin_credentials()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    if login.status_code != 200:
        return None
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def unique_code(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"
