"""Department API integration tests — require real MySQL (M2)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers_m2 import admin_headers, unique_code


@pytest.mark.asyncio
async def test_department_crud_and_tree(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    code = unique_code("DEPT")
    created = await client.post(
        "/api/v1/departments",
        headers=headers,
        json={
            "department_code": code,
            "department_name": "测试部门A",
            "status": "active",
        },
    )
    assert created.status_code == 201, created.text
    parent_id = created.json()["id"]

    child_code = unique_code("DEPT")
    child = await client.post(
        "/api/v1/departments",
        headers=headers,
        json={
            "department_code": child_code,
            "department_name": "测试子部门",
            "parent_id": parent_id,
        },
    )
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]

    # duplicate code -> 409
    dup = await client.post(
        "/api/v1/departments",
        headers=headers,
        json={"department_code": code, "department_name": "重复"},
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "conflict"

    # cycle -> 400/422
    cycle = await client.patch(
        f"/api/v1/departments/{parent_id}",
        headers=headers,
        json={"parent_id": child_id},
    )
    assert cycle.status_code in {400, 422}
    assert cycle.json()["code"] in {"validation_error", "business_rule_violation"}

    listed = await client.get(
        "/api/v1/departments",
        headers=headers,
        params={"keyword": code},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    tree = await client.get("/api/v1/departments/tree", headers=headers)
    assert tree.status_code == 200
    tree_text = tree.text
    assert code in tree_text

    updated = await client.patch(
        f"/api/v1/departments/{parent_id}",
        headers=headers,
        json={"department_name": "测试部门A改名"},
    )
    assert updated.status_code == 200
    assert updated.json()["department_name"] == "测试部门A改名"

    # disable parent while active child exists -> rejected
    disable = await client.patch(
        f"/api/v1/departments/{parent_id}",
        headers=headers,
        json={"status": "disabled"},
    )
    assert disable.status_code in {400, 422}

    # disable child first, then parent
    assert (
        await client.patch(
            f"/api/v1/departments/{child_id}",
            headers=headers,
            json={"status": "disabled"},
        )
    ).status_code == 200
    assert (
        await client.patch(
            f"/api/v1/departments/{parent_id}",
            headers=headers,
            json={"status": "disabled"},
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_department_not_found(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")
    resp = await client.get("/api/v1/departments/99999999", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "resource_not_found"
