"""Employee CRUD and Excel import/export integration tests (M2)."""

from __future__ import annotations

from io import BytesIO

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from tests.helpers_m2 import admin_headers, unique_code


def _workbook_bytes(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "员工导入"
    headers = [
        "员工工号",
        "员工姓名",
        "性别",
        "部门编码",
        "岗位",
        "入职日期",
        "联系电话",
        "用工类型",
        "班次",
        "是否需要住宿",
    ]
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_employee_crud_and_unique_no(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dept_code = unique_code("DEPT")
    dept = await client.post(
        "/api/v1/departments",
        headers=headers,
        json={"department_code": dept_code, "department_name": "员工测试部门"},
    )
    assert dept.status_code == 201
    department_id = dept.json()["id"]

    emp_no = unique_code("EMP")
    payload = {
        "employee_no": emp_no,
        "full_name": "测试员工",
        "gender": "male",
        "department_id": department_id,
        "position": "工程师",
        "employment_type": "full_time",
        "phone": "13800000000",
        "join_date": "2026-01-01",
        "employment_status": "active",
        "accommodation_required": True,
        "shift_type": "day",
    }
    created = await client.post("/api/v1/employees", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    emp_id = created.json()["id"]
    assert created.json()["employee_no"] == emp_no
    assert created.json()["department_code"] == dept_code

    dup = await client.post("/api/v1/employees", headers=headers, json=payload)
    assert dup.status_code == 409
    assert dup.json()["code"] == "conflict"

    updated = await client.patch(
        f"/api/v1/employees/{emp_id}",
        headers=headers,
        json={"full_name": "测试员工改名", "employment_status": "probation"},
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "测试员工改名"
    assert updated.json()["employment_status"] == "probation"

    listed = await client.get(
        "/api/v1/employees",
        headers=headers,
        params={"keyword": emp_no},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    detail = await client.get(f"/api/v1/employees/{emp_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == emp_id

    # M2: accommodation endpoints are empty but valid
    accom = await client.get(f"/api/v1/employees/{emp_id}/accommodation", headers=headers)
    assert accom.status_code == 200
    assert accom.json() is None
    history = await client.get(f"/api/v1/employees/{emp_id}/history", headers=headers)
    assert history.status_code == 200
    assert history.json() == []


@pytest.mark.asyncio
async def test_employee_date_validation(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")
    resp = await client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "employee_no": unique_code("EMP"),
            "full_name": "日期错误",
            "join_date": "2026-05-01",
            "termination_date": "2026-01-01",
        },
    )
    assert resp.status_code in {400, 422}


@pytest.mark.asyncio
async def test_employee_import_template_and_two_phase(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    template = await client.get("/api/v1/employees/import/template", headers=headers)
    assert template.status_code == 200
    assert template.content[:2] == b"PK"

    dept_code = unique_code("DEPT")
    dept = await client.post(
        "/api/v1/departments",
        headers=headers,
        json={"department_code": dept_code, "department_name": "导入测试部门"},
    )
    assert dept.status_code == 201

    new_no = unique_code("EMP")
    existing_no = unique_code("EMP")
    seed = await client.post(
        "/api/v1/employees",
        headers=headers,
        json={"employee_no": existing_no, "full_name": "已存在员工"},
    )
    assert seed.status_code == 201

    content = _workbook_bytes(
        [
            [
                new_no,
                "新员工甲",
                "男",
                dept_code,
                "专员",
                "2026-02-01",
                "13900000001",
                "正式",
                "白班",
                "是",
            ],
            [
                existing_no,
                "更新员工乙",
                "女",
                dept_code,
                "主管",
                "2026-02-02",
                "13900000002",
                "正式",
                "夜班",
                "否",
            ],
            ["", "空工号", "男", dept_code, "", "", "", "", "", ""],
            [
                unique_code("EMP"),
                "坏日期",
                "男",
                "NO_SUCH_DEPT",
                "",
                "not-a-date",
                "",
                "",
                "",
                "",
            ],
        ]
    )
    xlsx_ct = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    preview = await client.post(
        "/api/v1/employees/import/preview",
        headers=headers,
        files={"file": ("import.xlsx", content, xlsx_ct)},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    job_id = body["import_job_id"]
    assert body["total_rows"] == 4
    assert body["create_count"] >= 1
    assert body["update_count"] >= 1
    assert body["error_count"] >= 2

    # preview did not create employees yet
    before = await client.get(
        "/api/v1/employees", headers=headers, params={"keyword": new_no}
    )
    assert before.json()["total"] == 0

    commit = await client.post(
        "/api/v1/employees/import/commit",
        headers=headers,
        params={"import_job_id": job_id},
    )
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert result["created_count"] >= 1
    assert result["updated_count"] >= 1
    assert result["failed_rows"] >= 2

    after = await client.get(
        "/api/v1/employees", headers=headers, params={"keyword": new_no}
    )
    assert after.json()["total"] == 1

    job = await client.get(f"/api/v1/imports/{job_id}", headers=headers)
    assert job.status_code == 200
    assert job.json()["status"] in {"completed", "completed_with_errors"}

    errors = await client.get(f"/api/v1/imports/{job_id}/errors", headers=headers)
    assert errors.status_code == 200
    assert len(errors.json()) >= 2

    # double commit is rejected
    again = await client.post(
        "/api/v1/employees/import/commit",
        headers=headers,
        params={"import_job_id": job_id},
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_employee_export(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")
    resp = await client.get("/api/v1/employees/export", headers=headers)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"
