"""Code-review P1 reproductions (DMS-P1-001 … DMS-P1-004).

Real MySQL isolated test database. Each test constructs the failing
scenario first; after the corresponding fix the same test must pass.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from io import BytesIO

import pytest
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy import select

from app.models.base import utcnow
from app.models.employee import Employee
from app.models.import_job import ImportJob
from tests.helpers_m2 import admin_headers, unique_code
from tests.helpers_m3 import make_dorm, make_employee
from tests.helpers_m4 import checkin_employee


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


def _row_data(employee_no: str, full_name: str, **overrides) -> dict:
    data = {
        "employee_no": employee_no,
        "full_name": full_name,
        "gender": "male",
        "department_id": None,
        "department_code": None,
        "position": None,
        "employment_type": "full_time",
        "phone": None,
        "join_date": None,
        "accommodation_required": True,
        "shift_type": "day",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# DMS-P1-001 — per-row SAVEPOINT isolation on commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p1_001_import_partial_success_after_db_error(client: AsyncClient):
    """valid, DB-error, valid rows → 2 succeed, 1 fails, commit still lands.

    Middle row uses an employee_no longer than varchar(64) so MySQL
    STRICT_TRANS_TABLES raises DataError on INSERT — a real database error,
    not an application-level validation message.
    """
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    from app.core.database import AsyncSessionLocal

    ok_a = unique_code("P1A")
    bad_no = "Z" * 100  # > varchar(64)
    ok_c = unique_code("P1C")

    rows = [
        {
            "row_no": 2,
            "action": "create",
            "employee_no": ok_a,
            "full_name": "甲有效",
            "message": "new",
            "data": _row_data(ok_a, "甲有效"),
        },
        {
            "row_no": 3,
            "action": "create",
            "employee_no": bad_no,
            "full_name": "乙坏行",
            "message": "new",
            "data": _row_data(bad_no, "乙坏行"),
        },
        {
            "row_no": 4,
            "action": "create",
            "employee_no": ok_c,
            "full_name": "丙有效",
            "message": "new",
            "data": _row_data(ok_c, "丙有效"),
        },
    ]
    async with AsyncSessionLocal() as db:
        job = ImportJob(
            import_type="employee",
            filename="p1-001.xlsx",
            file_hash=unique_code("hash"),
            status="previewed",
            total_rows=3,
            success_rows=3,
            failed_rows=0,
            detail=json.dumps({"rows": rows}, ensure_ascii=False),
        )
        db.add(job)
        await db.commit()
        job_id = job.id

    commit = await client.post(
        "/api/v1/employees/import/commit",
        headers=headers,
        params={"import_job_id": job_id},
    )
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert result["created_count"] == 2
    assert result["updated_count"] == 0
    assert result["failed_rows"] == 1
    assert result["success_rows"] == 2
    assert len(result["errors"]) == 1

    listed = await client.get(
        "/api/v1/employees", headers=headers, params={"keyword": "P1"}
    )
    nos = {item["employee_no"] for item in listed.json()["items"]}
    assert ok_a in nos
    assert ok_c in nos

    job = await client.get(f"/api/v1/imports/{job_id}", headers=headers)
    assert job.json()["status"] == "completed_with_errors"
    assert job.json()["success_rows"] == 2
    assert job.json()["failed_rows"] == 1


@pytest.mark.asyncio
async def test_p1_001_import_audit_matches_persisted_rows(client: AsyncClient):
    """Audit commit summary must equal rows actually written."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    from app.core.database import AsyncSessionLocal

    ok_a = unique_code("P1AU")
    ok_b = unique_code("P1BU")
    bad_no = "Q" * 80

    rows = [
        {
            "row_no": 2,
            "action": "create",
            "employee_no": ok_a,
            "full_name": "审计甲",
            "message": "new",
            "data": _row_data(ok_a, "审计甲"),
        },
        {
            "row_no": 3,
            "action": "create",
            "employee_no": bad_no,
            "full_name": "审计坏",
            "message": "new",
            "data": _row_data(bad_no, "审计坏"),
        },
        {
            "row_no": 4,
            "action": "create",
            "employee_no": ok_b,
            "full_name": "审计乙",
            "message": "new",
            "data": _row_data(ok_b, "审计乙"),
        },
    ]
    async with AsyncSessionLocal() as db:
        job = ImportJob(
            import_type="employee",
            filename="p1-001-audit.xlsx",
            file_hash=unique_code("hash"),
            status="previewed",
            total_rows=3,
            success_rows=3,
            failed_rows=0,
            detail=json.dumps({"rows": rows}, ensure_ascii=False),
        )
        db.add(job)
        await db.commit()
        job_id = job.id

    commit = await client.post(
        "/api/v1/employees/import/commit",
        headers=headers,
        params={"import_job_id": job_id},
    )
    assert commit.status_code == 200, commit.text

    async with AsyncSessionLocal() as db:
        from sqlalchemy import text

        raw = (
            await db.execute(
                text(
                    "SELECT action, after_data FROM audit_logs "
                    "WHERE resource_type='import_job' AND resource_id=:rid "
                    "AND action='employee.import_commit'"
                ),
                {"rid": job_id},
            )
        ).all()
        assert raw, "import_commit audit row missing"
        payload = json.loads(raw[0][1])
        assert payload["created"] == 2
        assert payload["errors"] == 1

        count_a = (
            await db.execute(
                select(Employee).where(Employee.employee_no.in_([ok_a, ok_b]))
            )
        ).scalars().all()
        assert len(count_a) == 2


# ---------------------------------------------------------------------------
# DMS-P1-002 — preview/commit action must not silently flip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p1_002_preview_create_not_silently_updated(client: AsyncClient):
    """Preview says create; another session inserts the same employee_no.
    Commit must report a conflict for that row and must NOT overwrite."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    from app.core.database import AsyncSessionLocal

    emp_no = unique_code("P1C")
    content = _workbook_bytes([[emp_no, "预览新增名", "男", "", "", "", "", "正式", "白班", "是"]])
    preview = await client.post(
        "/api/v1/employees/import/preview",
        headers=headers,
        files={"file": ("import.xlsx", content, "application/octet-stream")},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["create_count"] == 1
    job_id = body["import_job_id"]

    # "another session" creates the employee with a different name
    async with AsyncSessionLocal() as db:
        db.add(
            Employee(
                employee_no=emp_no,
                full_name="对方写入",
                employment_status="active",
                phone="13911112222",
            )
        )
        await db.commit()

    commit = await client.post(
        "/api/v1/employees/import/commit",
        headers=headers,
        params={"import_job_id": job_id},
    )
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert result["created_count"] == 0
    assert result["updated_count"] == 0
    assert result["failed_rows"] == 1
    assert result["success_rows"] == 0
    assert any(
        emp_no in (e.get("message") or "") or e.get("employee_no") == emp_no
        for e in result["errors"]
    )

    # the other session's row is untouched
    listed = await client.get(
        "/api/v1/employees", headers=headers, params={"keyword": emp_no}
    )
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["full_name"] == "对方写入"
    assert items[0]["phone"] == "13911112222"


@pytest.mark.asyncio
async def test_p1_002_preview_update_not_silently_recreated(client: AsyncClient):
    """Preview says update; target is deleted before commit.
    Commit must report a conflict and must NOT re-create the employee."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    from app.core.database import AsyncSessionLocal

    emp_no = unique_code("P1U")
    seed = await client.post(
        "/api/v1/employees",
        headers=headers,
        json={"employee_no": emp_no, "full_name": "将被删除"},
    )
    assert seed.status_code == 201

    content = _workbook_bytes([[emp_no, "更新名", "女", "", "", "", "", "正式", "夜班", "否"]])
    preview = await client.post(
        "/api/v1/employees/import/preview",
        headers=headers,
        files={"file": ("import.xlsx", content, "application/octet-stream")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["update_count"] == 1
    job_id = preview.json()["import_job_id"]

    async with AsyncSessionLocal() as db:
        emp = (
            await db.execute(select(Employee).where(Employee.employee_no == emp_no))
        ).scalar_one()
        await db.delete(emp)
        await db.commit()

    commit = await client.post(
        "/api/v1/employees/import/commit",
        headers=headers,
        params={"import_job_id": job_id},
    )
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert result["created_count"] == 0
    assert result["updated_count"] == 0
    assert result["failed_rows"] == 1

    listed = await client.get(
        "/api/v1/employees", headers=headers, params={"keyword": emp_no}
    )
    assert listed.json()["total"] == 0


@pytest.mark.asyncio
async def test_p1_002_bulk_update_still_works_when_preview_matches(client: AsyncClient):
    """Documented behaviour: bulk update is allowed when preview action == update
    and the employee still exists at commit time."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    emp_no = unique_code("P1M")
    seed = await client.post(
        "/api/v1/employees",
        headers=headers,
        json={"employee_no": emp_no, "full_name": "旧名"},
    )
    assert seed.status_code == 201

    content = _workbook_bytes([[emp_no, "新名", "女", "", "", "", "", "正式", "夜班", "否"]])
    preview = await client.post(
        "/api/v1/employees/import/preview",
        headers=headers,
        files={"file": ("import.xlsx", content, "application/octet-stream")},
    )
    assert preview.json()["update_count"] == 1
    job_id = preview.json()["import_job_id"]

    commit = await client.post(
        "/api/v1/employees/import/commit",
        headers=headers,
        params={"import_job_id": job_id},
    )
    assert commit.status_code == 200, commit.text
    assert commit.json()["updated_count"] == 1

    listed = await client.get(
        "/api/v1/employees", headers=headers, params={"keyword": emp_no}
    )
    assert listed.json()["items"][0]["full_name"] == "新名"


# ---------------------------------------------------------------------------
# DMS-P1-004 — expired reservation must not be consumable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p1_004_confirm_rejects_expired_reservation(client: AsyncClient):
    """expires_at has passed but scanner has not run — confirm must 409."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")


    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="到期")
    bed_id = dorm["beds"][0]["id"]

    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp["id"]},
    )
    assert created.status_code == 201
    app_id = created.json()["id"]
    assert (
        await client.post(
            f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={}
        )
    ).status_code == 200

    past = (utcnow() - timedelta(hours=2)).isoformat()
    reserve = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id, "expires_at": past},
    )
    assert reserve.status_code == 200, reserve.text

    confirm = await client.post(
        f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
    )
    assert confirm.status_code == 409, confirm.text
    assert confirm.json()["code"] in {"conflict", "business_rule_violation"}

    # bed is still free (no silent occupancy)
    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    target = next(b for b in bed_list if b["id"] == bed_id)
    assert target["occupied"] is False


@pytest.mark.asyncio
async def test_p1_004_transfer_complete_rejects_expired_reservation(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=2)
    emp = await make_employee(client, headers, suffix="调宿到期")
    src_bed = dorm["beds"][0]["id"]
    dst_bed = dorm["beds"][1]["id"]

    await checkin_employee(client, headers, emp["id"], src_bed)

    created = await client.post(
        "/api/v1/transfers",
        headers=headers,
        json={"employee_id": emp["id"], "target_bed_id": dst_bed},
    )
    assert created.status_code in {200, 201}, created.text
    tr_id = created.json()["id"]

    past = (utcnow() - timedelta(hours=2)).isoformat()
    reserve = await client.post(
        f"/api/v1/transfers/{tr_id}/reserve",
        headers=headers,
        json={"target_bed_id": dst_bed, "expires_at": past},
    )
    assert reserve.status_code == 200, reserve.text

    complete = await client.post(
        f"/api/v1/transfers/{tr_id}/complete", headers=headers, json={}
    )
    assert complete.status_code == 409, complete.text

    # source occupancy remains active
    acc = await client.get(f"/api/v1/employees/{emp['id']}/accommodation", headers=headers)
    assert acc.json() is not None
    assert acc.json()["bed_id"] == src_bed


@pytest.mark.asyncio
async def test_p1_004_no_expiry_and_future_expiry_still_confirm(client: AsyncClient):
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    dorm = await make_dorm(client, headers, capacity=2)
    emp_a = await make_employee(client, headers, suffix="无过期")
    emp_b = await make_employee(client, headers, suffix="未到期")

    # no expires_at
    app = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp_a["id"]},
    )
    app_id = app.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={})
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": dorm["beds"][0]["id"]},
    )
    assert r.status_code == 200
    c = await client.post(
        f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
    )
    assert c.status_code == 200, c.text

    # future expires_at
    app = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp_b["id"]},
    )
    app_id = app.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={})
    future = (utcnow() + timedelta(days=1)).isoformat()
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": dorm["beds"][1]["id"], "expires_at": future},
    )
    assert r.status_code == 200
    c = await client.post(
        f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
    )
    assert c.status_code == 200, c.text


# ---------------------------------------------------------------------------
# DMS-P1-003 — scanner vs confirm lock order (deadlock / wait)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p1_003_confirm_and_expiry_scan_do_not_deadlock(client: AsyncClient):
    """Concurrent confirm-checkin and reservation expiry scan on the same
    reservation must finish without deadlock and keep invariants:
    either checked-in (scan must not free the bed) or expired (no occupancy).
    """
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    from app.core.database import AsyncSessionLocal
    from app.services import scanner_service

    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="死锁")
    bed_id = dorm["beds"][0]["id"]

    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp["id"]},
    )
    app_id = created.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={})

    # expires 1ms in the future so the scan sees it as expired almost immediately
    # while confirm is racing; use a past expiry after a tiny sleep inside the race
    # window instead: reserve with past expiry, then race confirm vs expire.
    past = (utcnow() - timedelta(minutes=1)).isoformat()
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id, "expires_at": past},
    )
    assert r.status_code == 200, r.text

    async def do_confirm():
        return await client.post(
            f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
        )

    async def do_scan():
        async with AsyncSessionLocal() as db:
            return await scanner_service.expire_reservations(db)

    # Run several rounds to catch lock-order issues
    for _ in range(3):
        # re-seed reservation each round if needed
        app_state = await client.get(
            f"/api/v1/checkin-applications/{app_id}", headers=headers
        )
        if app_state.json()["status"] == "checked_in":
            break
        if app_state.json()["status"] != "reserved":
            # recreate a fresh reserved application for another race
            break

        results = await asyncio.wait_for(
            asyncio.gather(do_confirm(), do_scan(), return_exceptions=True),
            timeout=15,
        )
        conf, scan = results
        if isinstance(conf, Exception):
            raise conf
        if isinstance(scan, Exception):
            raise scan

        state = await client.get(
            f"/api/v1/checkin-applications/{app_id}", headers=headers
        )
        status = state.json()["status"]
        beds = (
            await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)
        ).json()
        bed_list = beds["items"] if isinstance(beds, dict) else beds
        target = next(b for b in bed_list if b["id"] == bed_id)

        if status == "checked_in":
            assert target["occupied"] is True
            assert target["reserved"] is False
            break
        if status == "reserved":
            # scan expired it or left it; confirm may have failed with 409
            assert conf.status_code in {200, 409}, conf.text
            continue
        # expired application path: no silent double occupancy
        assert target["occupied"] is False


@pytest.mark.asyncio
async def test_p1_003_successful_checkin_not_undone_by_scan(client: AsyncClient):
    """After confirm succeeds, a later expiry scan must never free that bed.

    Covers the "reservation was consumed then expires_at has passed" path:
    status='consumed' rows are left alone and the occupancy stays active.
    """
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    from app.core.database import AsyncSessionLocal
    from app.services import scanner_service

    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="已入不撤销")
    bed_id = dorm["beds"][0]["id"]

    app = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp["id"]},
    )
    app_id = app.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={})
    # reserve with a short future expiry, confirm before it lapses
    soon = (utcnow() + timedelta(seconds=30)).isoformat()
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id, "expires_at": soon},
    )
    assert r.status_code == 200, r.text
    c = await client.post(
        f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
    )
    assert c.status_code == 200, c.text

    # Force the consumed reservation's expires_at into the past (scanner delay /
    # clock advance) and run the scan — occupancy must survive.
    async with AsyncSessionLocal() as db:
        from sqlalchemy import update

        from app.models.accommodation import BedReservation

        await db.execute(
            update(BedReservation)
            .where(BedReservation.employee_id == emp["id"])
            .values(expires_at=utcnow() - timedelta(hours=1))
        )
        await db.commit()
        await scanner_service.expire_reservations(db)

    beds = (await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)).json()
    bed_list = beds["items"] if isinstance(beds, dict) else beds
    target = next(b for b in bed_list if b["id"] == bed_id)
    assert target["occupied"] is True

    state = await client.get(f"/api/v1/checkin-applications/{app_id}", headers=headers)
    assert state.json()["status"] == "checked_in"


# ---------------------------------------------------------------------------
# DMS-P1-003 — lock-order regression (employee → bed → reservation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p1_003_scanner_lock_order_matches_design(client: AsyncClient):
    """Scanner must take locks in the documented order:
    employee FOR UPDATE → bed FOR UPDATE → reservation FOR UPDATE.
    Reversing reservation/bed locks is what created the deadlock window
    against confirm_checkin (employee → bed → reservation).
    """
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    from app.core.database import AsyncSessionLocal
    from app.services import occupancy as occ
    from app.services import scanner_service

    dorm = await make_dorm(client, headers, capacity=1)
    emp = await make_employee(client, headers, suffix="锁序")
    bed_id = dorm["beds"][0]["id"]

    created = await client.post(
        "/api/v1/checkin-applications",
        headers=headers,
        json={"employee_id": emp["id"]},
    )
    app_id = created.json()["id"]
    await client.post(f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={})
    past = (utcnow() - timedelta(minutes=5)).isoformat()
    r = await client.post(
        f"/api/v1/checkin-applications/{app_id}/reserve",
        headers=headers,
        json={"bed_id": bed_id, "expires_at": past},
    )
    assert r.status_code == 200, r.text

    order: list[str] = []
    orig_lock_employee = occ.lock_employee
    orig_lock_beds = occ.lock_beds

    async def spy_employee(db, employee_id):
        order.append(f"employee:{employee_id}")
        return await orig_lock_employee(db, employee_id)

    async def spy_beds(db, bed_ids):
        order.append("beds:" + ",".join(str(b) for b in sorted(bed_ids)))
        return await orig_lock_beds(db, bed_ids)

    occ.lock_employee = spy_employee  # type: ignore[assignment]
    occ.lock_beds = spy_beds  # type: ignore[assignment]
    try:
        async with AsyncSessionLocal() as db:
            await scanner_service.expire_reservations(db)
    finally:
        occ.lock_employee = orig_lock_employee  # type: ignore[assignment]
        occ.lock_beds = orig_lock_beds  # type: ignore[assignment]

    assert order, "scanner did not acquire any locks"
    emp_idx = next(i for i, s in enumerate(order) if s.startswith("employee:"))
    bed_idx = next(i for i, s in enumerate(order) if s.startswith("beds:"))
    assert emp_idx < bed_idx, f"lock order violated: {order}"
    # first pair must be the reserved employee/bed
    assert order[emp_idx] == f"employee:{emp['id']}"
    assert order[bed_idx] == f"beds:{bed_id}"


@pytest.mark.asyncio
async def test_p1_003_concurrent_confirm_vs_scan_many_rounds(client: AsyncClient):
    """Repeated confirm vs expiry-scan races must finish under a tight timeout
    (no deadlock/lock-wait) and leave a single legal occupancy state."""
    headers = await admin_headers(client)
    if headers is None:
        pytest.skip("Admin credentials not configured")

    from app.core.database import AsyncSessionLocal
    from app.services import scanner_service

    for round_no in range(5):
        dorm = await make_dorm(client, headers, capacity=1)
        emp = await make_employee(client, headers, suffix=f"竞{round_no}")
        bed_id = dorm["beds"][0]["id"]

        created = await client.post(
            "/api/v1/checkin-applications",
            headers=headers,
            json={"employee_id": emp["id"]},
        )
        app_id = created.json()["id"]
        await client.post(
            f"/api/v1/checkin-applications/{app_id}/approve", headers=headers, json={}
        )
        # Mix: some rounds use past expiry (confirm loses), some future (confirm wins)
        if round_no % 2 == 0:
            exp = (utcnow() - timedelta(seconds=5)).isoformat()
        else:
            exp = (utcnow() + timedelta(hours=1)).isoformat()
        r = await client.post(
            f"/api/v1/checkin-applications/{app_id}/reserve",
            headers=headers,
            json={"bed_id": bed_id, "expires_at": exp},
        )
        assert r.status_code == 200, r.text

        async def do_confirm(app_id=app_id):
            return await client.post(
                f"/api/v1/checkin-applications/{app_id}/confirm", headers=headers, json={}
            )

        async def do_scan():
            async with AsyncSessionLocal() as db:
                return await scanner_service.expire_reservations(db)

        conf, scan = await asyncio.wait_for(
            asyncio.gather(do_confirm(), do_scan(), return_exceptions=True),
            timeout=15,
        )
        assert not isinstance(conf, Exception), conf
        assert not isinstance(scan, Exception), scan

        state = await client.get(
            f"/api/v1/checkin-applications/{app_id}", headers=headers
        )
        status = state.json()["status"]
        beds = (
            await client.get(f"/api/v1/rooms/{dorm['room']['id']}/beds", headers=headers)
        ).json()
        bed_list = beds["items"] if isinstance(beds, dict) else beds
        target = next(b for b in bed_list if b["id"] == bed_id)

        if status == "checked_in":
            assert conf.status_code == 200
            assert target["occupied"] is True
            assert target["reserved"] is False
        else:
            # expired or conflict — bed must not be double-booked
            assert target["occupied"] is False
            assert conf.status_code in {200, 409}
