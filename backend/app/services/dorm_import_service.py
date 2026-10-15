"""V1.0.1 — room Excel import and batch bed allocation import.

Both flows: template → upload preview (validate) → confirm commit → row-level result.
Batch allocation reuses checkin_service for every row (no parallel business state machine).
Strategy: per-row SAVEPOINT (partial success), each row reports success/failure reason.
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    ResourceNotFound,
    ValidationError,
)
from app.models.dorm import DormArea, DormBed, DormBuilding, DormFloor, DormRoom
from app.models.employee import Employee
from app.schemas.dorm import RoomCreate
from app.services import audit_service, checkin_service, dorm_service

ROOM_IMPORT_COLUMNS = [
    ("area_code", "区域编码", True),
    ("building_code", "楼栋编码", True),
    ("floor_no", "楼层号", True),
    ("room_no", "房间号", True),
    ("room_type", "房型编码", False),
    ("capacity", "容量", True),
    ("gender_policy", "性别政策", False),
    ("access_code", "门禁密码", False),
    ("description", "备注", False),
]

ALLOC_IMPORT_COLUMNS = [
    ("employee_no", "员工工号", True),
    ("area_code", "区域编码", True),
    ("building_code", "楼栋编码", True),
    ("floor_no", "楼层号", True),
    ("room_no", "房间号", True),
    ("bed_no", "床位号", True),
]

MAX_IMPORT_ROWS = 2000


def _safe_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return value


def build_room_import_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "rooms"
    for col, (_key, label, required) in enumerate(ROOM_IMPORT_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=label)
        if required:
            cell.value = f"{label}*"
    notes = wb.create_sheet("notes")
    notes.cell(row=1, column=1, value="字段")
    notes.cell(row=1, column=2, value="说明")
    notes.cell(row=2, column=1, value="区域编码*")
    notes.cell(row=2, column=2, value="必须已存在")
    notes.cell(row=3, column=1, value="门禁密码")
    notes.cell(row=3, column=2, value="字符串，保留前导零；可空")
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_alloc_import_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "allocations"
    for col, (_key, label, required) in enumerate(ALLOC_IMPORT_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=label)
        if required:
            cell.value = f"{label}*"
    notes = wb.create_sheet("notes")
    notes.cell(row=1, column=1, value="说明")
    notes.cell(row=1, column=2, value="按员工工号+宿舍位置+床位号定位；逐行部分成功")
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _parse_rows(content: bytes, columns: list[tuple[str, str, bool]]) -> list[dict]:
    try:
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValidationError("无法解析 Excel 文件") from exc
    try:
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration:
            raise ValidationError("工作簿为空") from None
        key_by_label = {}
        for key, label, _req in columns:
            key_by_label[label] = key
            key_by_label[label.rstrip("*")] = key
            key_by_label[key] = key
        header_map: dict[int, str] = {}
        for idx, cell in enumerate(header or []):
            label = str(cell).strip() if cell is not None else ""
            mapped = key_by_label.get(label) or key_by_label.get(label.rstrip("*"))
            if mapped:
                header_map[idx] = mapped
        if not header_map:
            raise ValidationError("未识别到有效表头")
        out: list[dict] = []
        for excel_row, row in enumerate(rows_iter, start=2):
            if excel_row - 1 > MAX_IMPORT_ROWS:
                raise ValidationError(f"行数超过上限 {MAX_IMPORT_ROWS}")
            if row is None or all(c is None or str(c).strip() == "" for c in row):
                continue
            item = {"__row__": excel_row}
            for idx, key in header_map.items():
                item[key] = _safe_cell(row[idx] if idx < len(row) else None)
            out.append(item)
        return out
    finally:
        try:
            wb.close()
        except Exception:
            pass


async def _resolve_location(
    db: AsyncSession, *, area_code: Any, building_code: Any, floor_no: Any, room_no: Any
) -> dict:
    if not area_code or not building_code or floor_no in (None, "") or not room_no:
        raise ValidationError("区域/楼栋/楼层/房间 必填")
    area = (
        await db.execute(select(DormArea).where(DormArea.area_code == str(area_code)))
    ).scalar_one_or_none()
    if area is None:
        raise ValidationError(f"区域编码不存在: {area_code}")
    building = (
        await db.execute(
            select(DormBuilding).where(
                DormBuilding.area_id == area.id,
                DormBuilding.building_code == str(building_code),
            )
        )
    ).scalar_one_or_none()
    if building is None:
        raise ValidationError(f"楼栋编码不存在: {building_code}")
    try:
        floor_no_int = int(float(str(floor_no)))
    except ValueError as exc:
        raise ValidationError(f"楼层号无效: {floor_no}") from exc
    floor = (
        await db.execute(
            select(DormFloor).where(
                DormFloor.building_id == building.id, DormFloor.floor_no == floor_no_int
            )
        )
    ).scalar_one_or_none()
    if floor is None:
        raise ValidationError(f"楼层不存在: {floor_no}")
    room = (
        await db.execute(
            select(DormRoom).where(
                DormRoom.floor_id == floor.id, DormRoom.room_no == str(room_no)
            )
        )
    ).scalar_one_or_none()
    return {"area": area, "building": building, "floor": floor, "room": room}


async def preview_room_import(db: AsyncSession, content: bytes) -> dict:
    rows = _parse_rows(content, ROOM_IMPORT_COLUMNS)
    results = []
    seen_rooms: set[tuple[int, str]] = set()
    for row in rows:
        action = "create"
        errors: list[str] = []
        try:
            loc = await _resolve_location(
                db,
                area_code=row.get("area_code"),
                building_code=row.get("building_code"),
                floor_no=row.get("floor_no"),
                room_no=row.get("room_no"),
            )
            floor = loc["floor"]
            room = loc["room"]
            room_no = str(row.get("room_no"))
            if room is not None:
                action = "error"
                errors.append("房间编号在该楼层已存在，不覆盖已有住宿关系")
            key = (floor.id, room_no)
            if key in seen_rooms:
                action = "error"
                errors.append("文件内房间编号重复")
            seen_rooms.add(key)
            try:
                capacity = int(float(str(row.get("capacity"))))
            except (TypeError, ValueError):
                capacity = 0
            if capacity < 1 or capacity > 20:
                action = "error"
                errors.append(f"容量异常: {row.get('capacity')}")
            access_code = row.get("access_code")
            if access_code is not None and not isinstance(access_code, str):
                # preserve leading zeros: force string
                access_code = str(access_code)
        except (ValidationError, BusinessRuleError) as exc:
            action = "error"
            errors.append(str(exc))
        results.append(
            {
                "row": row.get("__row__"),
                "action": action,
                "message": "；".join(errors) if errors else None,
                "data": {k: row.get(k) for k, _l, _r in ROOM_IMPORT_COLUMNS},
            }
        )
    summary = {
        "total": len(results),
        "create": sum(1 for r in results if r["action"] == "create"),
        "error": sum(1 for r in results if r["action"] == "error"),
    }
    return {"rows": results, "summary": summary}


async def commit_room_import(
    db: AsyncSession, content: bytes, *, actor_user_id: int | None = None, request_id: str | None = None
) -> dict:
    preview = await preview_room_import(db, content)
    created = 0
    failed = 0
    for row, result in zip(_parse_rows(content, ROOM_IMPORT_COLUMNS), preview["rows"]):
        if result["action"] != "create":
            failed += 1
            continue
        try:
            loc = await _resolve_location(
                db,
                area_code=row.get("area_code"),
                building_code=row.get("building_code"),
                floor_no=row.get("floor_no"),
                room_no=row.get("room_no"),
            )
            capacity = int(float(str(row.get("capacity"))))
            access_code = row.get("access_code")
            if access_code is not None and not isinstance(access_code, str):
                access_code = str(access_code)
            payload = RoomCreate(
                floor_id=loc["floor"].id,
                room_no=str(row.get("room_no")),
                room_type=str(row.get("room_type") or "standard"),
                capacity=capacity,
                gender_policy=str(row.get("gender_policy") or "any"),
                description=str(row.get("description")) if row.get("description") else None,
                bed_count=capacity,
                access_code=access_code if access_code not in (None, "") else None,
            )
            # create_room commits internally; per-row partial success by try/except
            await dorm_service.create_room(
                db, payload, actor_user_id=actor_user_id, request_id=request_id
            )
            created += 1
        except Exception as exc:  # noqa: BLE001 — per-row isolation
            failed += 1
            result["action"] = "error"
            result["message"] = str(exc)
            try:
                await db.rollback()
            except Exception:
                pass
    await audit_service.write_audit(
        db,
        action="dorm_room.import",
        resource_type="import",
        resource_id=0,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={"created": created, "failed": failed},
    )
    await db.commit()
    return {
        "summary": {"created": created, "failed": failed, "total": preview["summary"]["total"]},
        "rows": preview["rows"],
        "strategy": "partial_success_per_row",
    }


async def preview_alloc_import(db: AsyncSession, content: bytes) -> dict:
    rows = _parse_rows(content, ALLOC_IMPORT_COLUMNS)
    results = []
    seen_emp: set[str] = set()
    seen_bed: set[tuple] = set()
    for row in rows:
        action = "allocate"
        errors: list[str] = []
        employee_no = str(row.get("employee_no") or "")
        if not employee_no:
            action = "error"
            errors.append("员工工号为空")
        elif employee_no in seen_emp:
            action = "error"
            errors.append("文件内员工工号重复")
        seen_emp.add(employee_no)
        try:
            loc = await _resolve_location(
                db,
                area_code=row.get("area_code"),
                building_code=row.get("building_code"),
                floor_no=row.get("floor_no"),
                room_no=row.get("room_no"),
            )
            room = loc["room"]
            if room is None:
                action = "error"
                errors.append("房间不存在")
            else:
                bed_no = str(row.get("bed_no") or "")
                bed = (
                    await db.execute(
                        select(DormBed).where(
                            DormBed.room_id == room.id, DormBed.bed_no == bed_no
                        )
                    )
                ).scalar_one_or_none()
                if bed is None:
                    action = "error"
                    errors.append(f"床位不存在: {bed_no}")
                else:
                    bkey = (bed.id,)
                    if bkey in seen_bed:
                        action = "error"
                        errors.append("文件内床位重复")
                    seen_bed.add(bkey)
                    emp = (
                        await db.execute(
                            select(Employee).where(Employee.employee_no == employee_no)
                        )
                    ).scalar_one_or_none()
                    if emp is None:
                        action = "error"
                        errors.append(f"员工不存在: {employee_no}")
                    elif not emp.accommodation_required:
                        action = "error"
                        errors.append("该员工不需要住宿，禁止分床")
        except (ValidationError, BusinessRuleError) as exc:
            action = "error"
            errors.append(str(exc))
        results.append(
            {
                "row": row.get("__row__"),
                "action": action,
                "message": "；".join(errors) if errors else None,
                "data": {k: row.get(k) for k, _l, _r in ALLOC_IMPORT_COLUMNS},
            }
        )
    summary = {
        "total": len(results),
        "allocate": sum(1 for r in results if r["action"] == "allocate"),
        "error": sum(1 for r in results if r["action"] == "error"),
    }
    return {"rows": results, "summary": summary}


async def _release_orphan_reservation(
    db: AsyncSession,
    *,
    application_id: int | None,
    employee_id: int,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> bool:
    """Safety net: if cancel_application failed, drop any leftover active reservation.

    Returns True when a reservation was released here.
    """
    from app.models.accommodation import BedReservation
    from app.models.base import utcnow

    stmt = select(BedReservation).where(
        BedReservation.status == "active",
        BedReservation.employee_id == employee_id,
    )
    if application_id is not None:
        stmt = stmt.where(BedReservation.application_id == application_id)
    rows = (await db.execute(stmt.with_for_update())).scalars().all()
    if not rows:
        return False
    for res in rows:
        res.status = "cancelled"
        res.released_at = utcnow()
        res.release_reason = "batch import failure recovery"
    await audit_service.write_audit(
        db,
        action="checkin.batch_allocate_import.recovery",
        resource_type="bed_reservation",
        resource_id=rows[0].id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={"released": len(rows), "employee_id": employee_id},
    )
    await db.commit()
    return True


async def commit_alloc_import(
    db: AsyncSession, content: bytes, *, actor_user_id: int | None = None, request_id: str | None = None
) -> dict:
    """Per-row partial success with safe failure recovery (UX-004 remediation).

    Each row: create_application → approve → reserve_bed → confirm_checkin (real state
    machine + BUG-007 checks). On failure:
      1. rollback any uncommitted work for that row
      2. cancel_application (releases active reservation)
      3. if that fails, force-release leftover active reservations for the employee
    Row results include action/message/recovery so the batch is auditable.
    Strategy: partial_success_per_row (never a silent half-state).
    """
    preview = await preview_alloc_import(db, content)
    succeeded = 0
    failed = 0
    recovered = 0
    parsed = _parse_rows(content, ALLOC_IMPORT_COLUMNS)

    for row, result in zip(parsed, preview["rows"]):
        # every row carries an explicit recovery marker for auditability
        if result["action"] != "allocate":
            result["recovery"] = "none"
            failed += 1
            continue

        app_id = None
        emp_id = None
        try:
            # fresh row transaction; drop anything dirty from previous row
            await db.rollback()

            emp = (
                await db.execute(
                    select(Employee).where(Employee.employee_no == str(row.get("employee_no")))
                )
            ).scalar_one_or_none()
            if emp is None:
                raise ResourceNotFound(f"员工不存在: {row.get('employee_no')}")
            emp_id = emp.id

            loc = await _resolve_location(
                db,
                area_code=row.get("area_code"),
                building_code=row.get("building_code"),
                floor_no=row.get("floor_no"),
                room_no=row.get("room_no"),
            )
            if loc["room"] is None:
                raise ResourceNotFound(f"房间不存在: {row.get('room_no')}")
            bed = (
                await db.execute(
                    select(DormBed).where(
                        DormBed.room_id == loc["room"].id,
                        DormBed.bed_no == str(row.get("bed_no")),
                    )
                )
            ).scalar_one_or_none()
            if bed is None:
                raise ResourceNotFound(f"床位不存在: {row.get('bed_no')}")

            try:
                app = await checkin_service.create_application(
                    db,
                    employee_id=emp.id,
                    application_type="new",
                    actor_user_id=actor_user_id,
                    request_id=request_id,
                )
                app_id = app["id"]
                await checkin_service.approve_application(
                    db, app_id, actor_user_id=actor_user_id, request_id=request_id
                )
                await checkin_service.reserve_bed(
                    db,
                    app_id,
                    bed_id=bed.id,
                    actor_user_id=actor_user_id,
                    request_id=request_id,
                )
                await checkin_service.confirm_checkin(
                    db, app_id, actor_user_id=actor_user_id, request_id=request_id
                )
                result["action"] = "success"
                result["message"] = f"已分配床位 {bed.bed_no}"
                result["recovery"] = "none"
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 — isolate row failure
                failed += 1
                result["action"] = "error"
                result["message"] = str(exc)
                try:
                    await db.rollback()
                except Exception:
                    pass
                cancelled = False
                if app_id is not None:
                    try:
                        await checkin_service.cancel_application(
                            db,
                            app_id,
                            reason="批量导入失败自动取消",
                            actor_user_id=actor_user_id,
                            request_id=request_id,
                        )
                        cancelled = True
                    except Exception as cancel_exc:  # noqa: BLE001
                        result["recovery"] = f"cancel_failed: {cancel_exc}"
                if emp_id is not None:
                    released = await _release_orphan_reservation(
                        db,
                        application_id=app_id,
                        employee_id=emp_id,
                        actor_user_id=actor_user_id,
                        request_id=request_id,
                    )
                    if released:
                        recovered += 1
                        result["recovery"] = "reservation_released"
                    elif cancelled:
                        result["recovery"] = "application_cancelled"
                    elif result.get("recovery") is None:
                        result["recovery"] = "rollback_only"
                elif result.get("recovery") is None:
                    result["recovery"] = "rollback_only"
        except Exception as exc:  # noqa: BLE001 — resolve-phase failures leave no writes
            failed += 1
            result["action"] = "error"
            result["message"] = str(exc)
            result["recovery"] = "none"
            try:
                await db.rollback()
            except Exception:
                pass

    await audit_service.write_audit(
        db,
        action="checkin.batch_allocate_import",
        resource_type="import",
        resource_id=0,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={
            "succeeded": succeeded,
            "failed": failed,
            "recovered": recovered,
            "strategy": "partial_success_per_row",
        },
    )
    await db.commit()
    return {
        "summary": {
            "succeeded": succeeded,
            "failed": failed,
            "recovered": recovered,
            "total": preview["summary"]["total"],
        },
        "rows": preview["rows"],
        "strategy": "partial_success_per_row",
    }
