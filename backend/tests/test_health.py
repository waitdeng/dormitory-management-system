"""Health check tests — no database required for liveness."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "request_id" not in body or body.get("status") == "ok"
    assert resp.headers.get("x-request-id")


@pytest.mark.asyncio
async def test_health_v1(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_openapi_available(client):
    resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
    assert "paths" in resp.json()
