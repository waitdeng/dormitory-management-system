"""Code-review P2/P3 tests (DMS-P2-005 … DMS-P2-007).

Real MySQL isolated test database for concurrency; config tests are pure.
"""

from __future__ import annotations

import asyncio
import json
from io import BytesIO

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from tests.helpers_m2 import admin_headers, unique_code
from tests.test_code_review_p1 import _row_data


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


def _make_job(job_id_placeholder=None, employee_no: str = "", filename: str = "p2.xlsx"):
    from app.models.import_job import ImportJob

    rows = [
        {
            "row_no": 2,
            "action": "create",
            "employee_no": employee_no,
            "full_name": "P2并发",
            "message": "new",
            "data": _row_data(employee_no, "P2并发"),
        }
    ]
    return ImportJob(
        import_type="employee",
        filename=filename,
        file_hash=unique_code("hash"),
        status="previewed",
        total_rows=1,
        success_rows=1,
        failed_rows=0,
        detail=json.dumps({"rows": rows}, ensure_ascii=False),
    )


# ---------------------------------------------------------------------------
# DMS-P2-005 — concurrent commit of the same import job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p2_005_concurrent_commit_same_import_job(client: AsyncClient):
    """Two simultaneous commits of one import job: exactly one applies the
    rows; the other gets a conflict. No duplicate employees / audit rows."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    from app.core.database import AsyncSessionLocal

    emp_no = unique_code("P2C")
    async with AsyncSessionLocal() as db:
        job = _make_job(employee_no=emp_no)
        db.add(job)
        await db.commit()
        job_id = job.id

    r1, r2 = await asyncio.gather(
        client.post(
            "/api/v1/employees/import/commit",
            headers=headers,
            params={"import_job_id": job_id},
        ),
        client.post(
            "/api/v1/employees/import/commit",
            headers=headers,
            params={"import_job_id": job_id},
        ),
    )
    codes = sorted([r1.status_code, r2.status_code])
    # One success; the loser is 409 (already claimed) or also 200 if it
    # observed the already-finalised job and hit the "already X" check.
    assert codes[0] == 200, f"expected one success: {r1.text} / {r2.text}"
    assert codes[1] in {200, 409}, f"unexpected loser status: {r1.status_code}/{r2.status_code}"
    if codes[1] == 200:
        # Sequential-safe path: second must not create a duplicate
        assert (r1.json()["created_count"] + r2.json()["created_count"]) == 1
    else:
        assert (r1.status_code == 409) != (r2.status_code == 409)
        winner = r1 if r1.status_code == 200 else r2
        assert winner.json()["created_count"] == 1

    listed = await client.get(
        "/api/v1/employees", headers=headers, params={"keyword": emp_no}
    )
    assert listed.json()["total"] == 1

    async with AsyncSessionLocal() as db:
        from sqlalchemy import text

        n = (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM employees WHERE employee_no = :no"
                ),
                {"no": emp_no},
            )
        ).scalar_one()
        assert n == 1


@pytest.mark.asyncio
async def test_p2_005_sequential_double_commit_rejected(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    emp_no = unique_code("P2S")
    content = _workbook_bytes([[emp_no, "顺序", "男", "", "", "", "", "正式", "白班", "是"]])
    preview = await client.post(
        "/api/v1/employees/import/preview",
        headers=headers,
        files={"file": ("import.xlsx", content, "application/octet-stream")},
    )
    assert preview.status_code == 200, preview.text
    job_id = preview.json()["import_job_id"]

    c1 = await client.post(
        "/api/v1/employees/import/commit",
        headers=headers,
        params={"import_job_id": job_id},
    )
    assert c1.status_code == 200
    c2 = await client.post(
        "/api/v1/employees/import/commit",
        headers=headers,
        params={"import_job_id": job_id},
    )
    assert c2.status_code == 409
    assert c2.json()["code"] == "conflict"


# ---------------------------------------------------------------------------
# DMS-P2-006 — workbook always closed on validation failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p2_006_preview_releases_workbook_on_bad_files(client: AsyncClient):
    """Malformed / header-missing / empty workbooks must not leak open handles.

    After each failed preview the preview path is exercised again with a good
    file — if a handle were leaked the openpyxl zip reader would eventually
    fail or leave the session stuck. We also assert the error is a clean 400.
    """
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    cases = []

    # 1) empty workbook (no rows)
    wb = Workbook()
    buf = BytesIO()
    wb.save(buf)
    cases.append(buf.getvalue())

    # 2) missing required columns
    wb = Workbook()
    ws = wb.active
    ws.append(["无关列A", "无关列B"])
    ws.append(["x", "y"])
    buf = BytesIO()
    wb.save(buf)
    cases.append(buf.getvalue())

    # 3) valid headers but zero data rows
    wb = Workbook()
    ws = wb.active
    ws.append(
        [
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
    )
    buf = BytesIO()
    wb.save(buf)
    cases.append(buf.getvalue())

    # 4) not a zip/xlsx
    cases.append(b"this is not a workbook")

    # 5) over-sized workbook ( > 5MB )
    cases.append(b"0" * (5 * 1024 * 1024 + 1))

    for idx, content in enumerate(cases):
        resp = await client.post(
            "/api/v1/employees/import/preview",
            headers=headers,
            files={"file": (f"bad-{idx}.xlsx", content, "application/octet-stream")},
        )
        assert resp.status_code in {400, 422}, f"case {idx}: {resp.status_code} {resp.text[:200]}"
        assert resp.json()["code"] in {"validation_error", "business_rule_violation", "conflict"}

    # A valid preview still works afterwards (no stuck resources)
    emp_no = unique_code("P2OK")
    content = _workbook_bytes([[emp_no, "善后", "男", "", "", "", "", "正式", "白班", "是"]])
    ok = await client.post(
        "/api/v1/employees/import/preview",
        headers=headers,
        files={"file": ("good.xlsx", content, "application/octet-stream")},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["create_count"] == 1


# ---------------------------------------------------------------------------
# DMS-P2-007 — API docs default
# ---------------------------------------------------------------------------


def test_p2_007_api_docs_setting_defaults():
    """ENABLE_API_DOCS must default to False so production does not expose
    /api/docs without an explicit opt-in. Non-production APP_ENV still
    exposes docs via main.create_app (`ENABLE_API_DOCS or APP_ENV != production`).
    """
    from app.core.config import Settings

    s = Settings(_env_file=None)
    assert s.ENABLE_API_DOCS is False

    def expose_docs(enable_flag: bool, app_env: str) -> bool:
        # mirrors main.create_app
        return enable_flag or app_env != "production"

    assert expose_docs(s.ENABLE_API_DOCS, "production") is False
    assert expose_docs(True, "production") is True  # explicit opt-in
    assert expose_docs(s.ENABLE_API_DOCS, "development") is True
    assert expose_docs(s.ENABLE_API_DOCS, "test") is True
