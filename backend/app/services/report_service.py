"""Report queries and Excel export (M5). All figures derive from authoritative records."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accommodation import (
    AccommodationRecord,
    BedReservation,
    TransferRecord,
)
from app.models.department import Department
from app.models.dorm import DormBed, DormBuilding, DormFloor, DormRoom
from app.models.employee import Employee
from app.models.workflow import WorkflowAlert
from app.services.data_scope import DeptScope, apply_employee_scope

_REPORT_TYPES = (
    "accommodations",
    "vacant-beds",
    "departments",
    "checkin-checkout",
    "transfers",
    "exceptions",
)


def _safe_excel_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _sheet_from_rows(ws, headers: list[str], rows: list[list[Any]]) -> None:
    ws.append(headers)
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    for row in rows:
        ws.append([_safe_excel_value(v) for v in row])
    for col_idx, header in enumerate(headers, start=1):
        width = max(12, min(36, len(str(header)) + 4))
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width


def _bed_chain_join():
    return (
        DormBed.__table__.join(DormRoom, DormBed.room_id == DormRoom.id)
        .join(DormFloor, DormRoom.floor_id == DormFloor.id)
        .join(DormBuilding, DormFloor.building_id == DormBuilding.id)
    )


async def _employee_map(db: AsyncSession, ids: set[int]) -> dict[int, Employee]:
    if not ids:
        return {}
    rows = (await db.execute(select(Employee).where(Employee.id.in_(ids)))).scalars().all()
    return {r.id: r for r in rows}


async def _department_map(db: AsyncSession, ids: set[int]) -> dict[int, Department]:
    if not ids:
        return {}
    rows = (await db.execute(select(Department).where(Department.id.in_(ids)))).scalars().all()
    return {r.id: r for r in rows}


# ---------------------------------------------------------------------------
# Accommodations ledger (current housing)
# ---------------------------------------------------------------------------


async def report_accommodations(
    db: AsyncSession,
    *,
    scope: DeptScope,
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
    department_id: int | None = None,
    building_id: int | None = None,
) -> tuple[list[dict], int]:
    """Active accommodation ledger. Includes offboarding/terminated employees still housed."""
    query = select(AccommodationRecord).where(AccommodationRecord.status == "active")
    count_query = (
        select(func.count())
        .select_from(AccommodationRecord)
        .where(AccommodationRecord.status == "active")
    )

    if department_id is not None:
        emp_ids_in_dept = select(Employee.id).where(Employee.department_id == department_id)
        query = query.where(AccommodationRecord.employee_id.in_(emp_ids_in_dept))
        count_query = count_query.where(AccommodationRecord.employee_id.in_(emp_ids_in_dept))

    query = apply_employee_scope(query, scope, AccommodationRecord.employee_id)
    count_query = apply_employee_scope(count_query, scope, AccommodationRecord.employee_id)

    if building_id is not None:
        bed_ids = (
            select(DormBed.id)
            .select_from(_bed_chain_join())
            .where(DormFloor.building_id == building_id)
        )
        query = query.where(AccommodationRecord.bed_id.in_(bed_ids))
        count_query = count_query.where(AccommodationRecord.bed_id.in_(bed_ids))

    if keyword:
        emp_kw = select(Employee.id).where(
            or_(
                Employee.employee_no.ilike(f"%{keyword}%"),
                Employee.full_name.ilike(f"%{keyword}%"),
            )
        )
        query = query.where(AccommodationRecord.employee_id.in_(emp_kw))
        count_query = count_query.where(AccommodationRecord.employee_id.in_(emp_kw))

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(AccommodationRecord.checkin_at.desc(), AccommodationRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    emps = await _employee_map(db, {r.employee_id for r in rows})
    depts = await _department_map(
        db, {e.department_id for e in emps.values() if e.department_id}
    )
    items: list[dict] = []
    for rec in rows:
        emp = emps.get(rec.employee_id)
        dept = depts.get(emp.department_id) if emp and emp.department_id else None
        chain = await _bed_location(db, rec.bed_id)
        items.append(
            {
                "id": rec.id,
                "employee_id": rec.employee_id,
                "employee_no": emp.employee_no if emp else None,
                "employee_name": emp.full_name if emp else None,
                "employment_status": emp.employment_status if emp else None,
                "gender": emp.gender if emp else None,
                "department_id": emp.department_id if emp else None,
                "department_code": dept.department_code if dept else None,
                "department_name": dept.department_name if dept else None,
                "bed_id": rec.bed_id,
                "bed_no": chain.get("bed_no"),
                "room_no": chain.get("room_no"),
                "floor_no": chain.get("floor_no"),
                "building_name": chain.get("building_name"),
                "area_name": chain.get("area_name"),
                "checkin_at": rec.checkin_at,
                "status": rec.status,
            }
        )
    return items, total


async def _bed_location(db: AsyncSession, bed_id: int) -> dict:
    from app.services import occupancy as occ

    try:
        chain = await occ.load_bed_chain(db, bed_id)
    except Exception:
        return {}
    return {
        "bed_no": chain["bed"].bed_no,
        "room_no": chain["room"].room_no,
        "floor_no": chain["floor"].floor_no,
        "building_name": chain["building"].building_name,
        "area_name": chain["area"].area_name,
    }


# ---------------------------------------------------------------------------
# Vacant beds
# ---------------------------------------------------------------------------


async def report_vacant_beds(
    db: AsyncSession,
    *,
    scope: DeptScope | None = None,
    page: int = 1,
    page_size: int = 50,
    building_id: int | None = None,
    floor_id: int | None = None,
    include_maintenance: bool = False,
) -> tuple[list[dict], int]:
    """Beds that can be allocated: operational_status=active, not occupied, not reserved.

    Reserved beds are NOT free. Maintenance/disabled beds are excluded unless
    include_maintenance is set (then returned with their status, still not free).
    """
    base = (
        select(DormBed.id)
        .select_from(
            DormBed.__table__.join(DormRoom, DormBed.room_id == DormRoom.id)
            .join(DormFloor, DormRoom.floor_id == DormFloor.id)
            .join(DormBuilding, DormFloor.building_id == DormBuilding.id)
        )
        .where(
            DormBed.operational_status == "active"
            if not include_maintenance
            else DormBed.operational_status.in_(("active", "maintenance", "disabled"))
        )
    )
    if building_id is not None:
        base = base.where(DormFloor.building_id == building_id)
    if floor_id is not None:
        base = base.where(DormRoom.floor_id == floor_id)

    occupied = select(AccommodationRecord.bed_id).where(AccommodationRecord.status == "active")
    reserved = select(BedReservation.bed_id).where(BedReservation.status == "active")
    free_ids_q = base.where(DormBed.id.not_in(occupied), DormBed.id.not_in(reserved))

    all_ids = (await db.execute(free_ids_q)).scalars().all()
    total = len(all_ids)
    page_ids = all_ids[(page - 1) * page_size : (page - 1) * page_size + page_size]
    if not page_ids:
        return [], total

    beds = (
        await db.execute(select(DormBed).where(DormBed.id.in_(page_ids)))
    ).scalars().all()
    bed_map = {b.id: b for b in beds}
    ordered = [bed_map[i] for i in page_ids if i in bed_map]

    items: list[dict] = []
    for bed in ordered:
        loc = await _bed_location(db, bed.id)
        items.append(
            {
                "bed_id": bed.id,
                "bed_no": bed.bed_no,
                "operational_status": bed.operational_status,
                "room_id": bed.room_id,
                **loc,
            }
        )
    return items, total


# ---------------------------------------------------------------------------
# Department statistics
# ---------------------------------------------------------------------------


async def report_departments(
    db: AsyncSession,
    *,
    scope: DeptScope,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """Housed / reserved / capacity counts per department (current, not historical)."""
    depts = (
        await db.execute(select(Department).order_by(Department.department_code))
    ).scalars().all()
    if not scope.is_full:
        allowed = scope.department_ids or frozenset()
        depts = [d for d in depts if d.id in allowed]
    total = len(depts)
    page_depts = depts[(page - 1) * page_size : (page - 1) * page_size + page_size]

    emp_dept_rows = (
        await db.execute(
            select(Employee.id, Employee.department_id).where(Employee.department_id.is_not(None))
        )
    ).all()
    emp_to_dept = {r[0]: r[1] for r in emp_dept_rows}

    housed = (
        await db.execute(
            select(AccommodationRecord.employee_id).where(AccommodationRecord.status == "active")
        )
    ).scalars().all()
    reserved = (
        await db.execute(
            select(BedReservation.employee_id).where(BedReservation.status == "active")
        )
    ).scalars().all()

    housed_by_dept: dict[int, int] = {}
    for eid in housed:
        d = emp_to_dept.get(eid)
        if d is not None:
            housed_by_dept[d] = housed_by_dept.get(d, 0) + 1
    reserved_by_dept: dict[int, int] = {}
    for eid in reserved:
        d = emp_to_dept.get(eid)
        if d is not None:
            reserved_by_dept[d] = reserved_by_dept.get(d, 0) + 1

    emp_count_rows = (
        await db.execute(
            select(Employee.department_id, func.count()).group_by(Employee.department_id)
        )
    ).all()
    emp_by_dept = {r[0]: r[1] for r in emp_count_rows if r[0] is not None}

    items = [
        {
            "department_id": d.id,
            "department_code": d.department_code,
            "department_name": d.department_name,
            "parent_id": d.parent_id,
            "employee_count": emp_by_dept.get(d.id, 0),
            "housed_count": housed_by_dept.get(d.id, 0),
            "reserved_count": reserved_by_dept.get(d.id, 0),
        }
        for d in page_depts
    ]
    return items, total


# ---------------------------------------------------------------------------
# Check-in / check-out detail
# ---------------------------------------------------------------------------


async def report_checkin_checkout(
    db: AsyncSession,
    *,
    scope: DeptScope,
    page: int = 1,
    page_size: int = 50,
    date_from: date | None = None,
    date_to: date | None = None,
    event_type: str | None = None,
) -> tuple[list[dict], int]:
    """Unified check-in / check-out events from accommodation_records history."""
    query = select(AccommodationRecord)
    count_query = select(func.count()).select_from(AccommodationRecord)

    def _filters(stmt):
        stmt = apply_employee_scope(stmt, scope, AccommodationRecord.employee_id)
        if event_type == "checkin":
            stmt = stmt.where(AccommodationRecord.checkin_at.is_not(None))
        elif event_type == "checkout":
            stmt = stmt.where(AccommodationRecord.checkout_at.is_not(None))
        return stmt

    # date filter applied after building events
    total = (await db.execute(_filters(count_query))).scalar_one()
    rows = (
        await db.execute(
            _filters(query.order_by(AccommodationRecord.id.desc())).limit(2000)
        )
    ).scalars().all()

    events: list[dict] = []
    emps = await _employee_map(db, {r.employee_id for r in rows})
    depts = await _department_map(db, {e.department_id for e in emps.values() if e.department_id})

    for rec in rows:
        emp = emps.get(rec.employee_id)
        dept = depts.get(emp.department_id) if emp and emp.department_id else None
        loc = await _bed_location(db, rec.bed_id)
        base = {
            "employee_id": rec.employee_id,
            "employee_no": emp.employee_no if emp else None,
            "employee_name": emp.full_name if emp else None,
            "department_name": dept.department_name if dept else None,
            "bed_id": rec.bed_id,
            **loc,
        }
        if event_type in (None, "checkin") and rec.checkin_at is not None:
            events.append(
                {
                    **base,
                    "event_type": "checkin",
                    "event_at": rec.checkin_at,
                    "reason": None,
                    "accommodation_id": rec.id,
                }
            )
        if event_type in (None, "checkout") and rec.checkout_at is not None:
            events.append(
                {
                    **base,
                    "event_type": "checkout",
                    "event_at": rec.checkout_at,
                    "reason": rec.end_reason,
                    "accommodation_id": rec.id,
                }
            )

    if date_from:
        events = [e for e in events if e["event_at"].date() >= date_from]
    if date_to:
        events = [e for e in events if e["event_at"].date() <= date_to]
    events.sort(key=lambda e: e["event_at"], reverse=True)
    total = len(events)
    page_events = events[(page - 1) * page_size : (page - 1) * page_size + page_size]
    return page_events, total


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------


async def report_transfers(
    db: AsyncSession,
    *,
    scope: DeptScope,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
) -> tuple[list[dict], int]:
    query = select(TransferRecord)
    count_query = select(func.count()).select_from(TransferRecord)
    query = apply_employee_scope(query, scope, TransferRecord.employee_id)
    count_query = apply_employee_scope(count_query, scope, TransferRecord.employee_id)
    if status:
        query = query.where(TransferRecord.status == status)
        count_query = count_query.where(TransferRecord.status == status)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(TransferRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    emps = await _employee_map(db, {r.employee_id for r in rows})
    depts = await _department_map(db, {e.department_id for e in emps.values() if e.department_id})
    items = []
    for rec in rows:
        emp = emps.get(rec.employee_id)
        dept = depts.get(emp.department_id) if emp and emp.department_id else None
        old_loc = await _bed_location(db, rec.source_bed_id) if rec.source_bed_id else {}
        new_loc = await _bed_location(db, rec.target_bed_id) if rec.target_bed_id else {}
        items.append(
            {
                "id": rec.id,
                "transfer_no": rec.transfer_no,
                "employee_id": rec.employee_id,
                "employee_no": emp.employee_no if emp else None,
                "employee_name": emp.full_name if emp else None,
                "department_name": dept.department_name if dept else None,
                "old_bed_id": rec.source_bed_id,
                "old_location": old_loc,
                "new_bed_id": rec.target_bed_id,
                "new_location": new_loc,
                "status": rec.status,
                "reason": rec.reason,
                "created_at": rec.requested_at,
                "completed_at": rec.completed_at,
            }
        )
    return items, total


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


async def report_exceptions(
    db: AsyncSession,
    *,
    scope: DeptScope,
    page: int = 1,
    page_size: int = 50,
    status: str | None = "active",
    alert_type: str | None = None,
) -> tuple[list[dict], int]:
    query = select(WorkflowAlert)
    count_query = select(func.count()).select_from(WorkflowAlert)
    query = apply_employee_scope(query, scope, WorkflowAlert.employee_id)
    count_query = apply_employee_scope(count_query, scope, WorkflowAlert.employee_id)
    if status:
        query = query.where(WorkflowAlert.status == status)
        count_query = count_query.where(WorkflowAlert.status == status)
    if alert_type:
        query = query.where(WorkflowAlert.alert_type == alert_type)
        count_query = count_query.where(WorkflowAlert.alert_type == alert_type)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(WorkflowAlert.detected_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    emps = await _employee_map(db, {r.employee_id for r in rows if r.employee_id})
    depts = await _department_map(db, {e.department_id for e in emps.values() if e.department_id})
    items = []
    for rec in rows:
        emp = emps.get(rec.employee_id) if rec.employee_id else None
        dept = depts.get(emp.department_id) if emp and emp.department_id else None
        items.append(
            {
                "id": rec.id,
                "alert_type": rec.alert_type,
                "severity": rec.severity,
                "employee_id": rec.employee_id,
                "employee_no": emp.employee_no if emp else None,
                "employee_name": emp.full_name if emp else None,
                "department_name": dept.department_name if dept else None,
                "title": rec.title,
                "detail": rec.detail,
                "status": rec.status,
                "detected_at": rec.detected_at,
                "resolved_at": rec.resolved_at,
            }
        )
    return items, total


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

_EXPORT_MAX = 5000


async def export_report(
    db: AsyncSession,
    report_type: str,
    *,
    scope: DeptScope,
    **filters: Any,
) -> bytes:
    if report_type not in _REPORT_TYPES:
        raise ValueError(f"unknown report_type '{report_type}'")

    wb = Workbook()
    ws = wb.active
    ws.title = report_type[:31]

    if report_type == "accommodations":
        items, _ = await report_accommodations(
            db,
            scope=scope,
            page=1,
            page_size=_EXPORT_MAX,
            keyword=filters.get("keyword"),
            department_id=filters.get("department_id"),
            building_id=filters.get("building_id"),
        )
        _sheet_from_rows(
            ws,
            [
                "工号",
                "姓名",
                "人事状态",
                "性别",
                "部门编码",
                "部门名称",
                "区域",
                "楼栋",
                "楼层",
                "房间",
                "床位",
                "入住时间",
            ],
            [
                [
                    i["employee_no"],
                    i["employee_name"],
                    i["employment_status"],
                    i["gender"],
                    i["department_code"],
                    i["department_name"],
                    i["area_name"],
                    i["building_name"],
                    i["floor_no"],
                    i["room_no"],
                    i["bed_no"],
                    i["checkin_at"].isoformat() if i["checkin_at"] else None,
                ]
                for i in items
            ],
        )
    elif report_type == "vacant-beds":
        items, _ = await report_vacant_beds(
            db,
            page=1,
            page_size=_EXPORT_MAX,
            building_id=filters.get("building_id"),
            floor_id=filters.get("floor_id"),
        )
        _sheet_from_rows(
            ws,
            ["区域", "楼栋", "楼层", "房间", "床位", "床位状态"],
            [
                [
                    i["area_name"],
                    i["building_name"],
                    i["floor_no"],
                    i["room_no"],
                    i["bed_no"],
                    i["operational_status"],
                ]
                for i in items
            ],
        )
    elif report_type == "departments":
        items, _ = await report_departments(db, scope=scope, page=1, page_size=_EXPORT_MAX)
        _sheet_from_rows(
            ws,
            ["部门编码", "部门名称", "员工数", "在住人数", "已预留人数"],
            [
                [
                    i["department_code"],
                    i["department_name"],
                    i["employee_count"],
                    i["housed_count"],
                    i["reserved_count"],
                ]
                for i in items
            ],
        )
    elif report_type == "checkin-checkout":
        items, _ = await report_checkin_checkout(
            db,
            scope=scope,
            page=1,
            page_size=_EXPORT_MAX,
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
            event_type=filters.get("event_type"),
        )
        _sheet_from_rows(
            ws,
            [
                "事件类型", "时间", "工号", "姓名", "部门",
                "区域", "楼栋", "楼层", "房间", "床位", "原因",
            ],
            [
                [
                    i["event_type"],
                    i["event_at"].isoformat() if i["event_at"] else None,
                    i["employee_no"],
                    i["employee_name"],
                    i["department_name"],
                    i["area_name"],
                    i["building_name"],
                    i["floor_no"],
                    i["room_no"],
                    i["bed_no"],
                    i["reason"],
                ]
                for i in items
            ],
        )
    elif report_type == "transfers":
        items, _ = await report_transfers(
            db,
            scope=scope,
            page=1,
            page_size=_EXPORT_MAX,
            status=filters.get("status"),
        )
        _sheet_from_rows(
            ws,
            [
                "调宿单号",
                "工号",
                "姓名",
                "部门",
                "原床位",
                "新床位",
                "状态",
                "原因",
                "创建时间",
                "完成时间",
            ],
            [
                [
                    i["transfer_no"],
                    i["employee_no"],
                    i["employee_name"],
                    i["department_name"],
                    _fmt_loc(i["old_location"]),
                    _fmt_loc(i["new_location"]),
                    i["status"],
                    i["reason"],
                    i["created_at"].isoformat() if i["created_at"] else None,
                    i["completed_at"].isoformat() if i["completed_at"] else None,
                ]
                for i in items
            ],
        )
    elif report_type == "exceptions":
        items, _ = await report_exceptions(
            db,
            scope=scope,
            page=1,
            page_size=_EXPORT_MAX,
            status=filters.get("status", "active"),
            alert_type=filters.get("alert_type"),
        )
        _sheet_from_rows(
            ws,
            ["预警类型", "严重级别", "工号", "姓名", "部门", "标题", "详情", "状态", "发现时间"],
            [
                [
                    i["alert_type"],
                    i["severity"],
                    i["employee_no"],
                    i["employee_name"],
                    i["department_name"],
                    i["title"],
                    i["detail"],
                    i["status"],
                    i["detected_at"].isoformat() if i["detected_at"] else None,
                ]
                for i in items
            ],
        )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _fmt_loc(loc: dict | None) -> str:
    if not loc:
        return ""
    return f"{loc.get('building_name', '')}/{loc.get('room_no', '')}/{loc.get('bed_no', '')}"
