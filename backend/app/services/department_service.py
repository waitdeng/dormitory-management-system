"""Department service — CRUD with cycle prevention and audit (M2)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ResourceNotFound, ValidationError
from app.models.department import Department
from app.models.employee import Employee
from app.schemas.department import DepartmentCreate, DepartmentUpdate
from app.services import audit_service


def _to_out(dept: Department) -> dict:
    return {
        "id": dept.id,
        "department_code": dept.department_code,
        "department_name": dept.department_name,
        "parent_id": dept.parent_id,
        "manager_employee_id": dept.manager_employee_id,
        "status": dept.status,
        "created_at": dept.created_at,
        "updated_at": dept.updated_at,
    }


async def _load(db: AsyncSession, dept_id: int) -> Department:
    dept = (
        await db.execute(
            select(Department)
            .where(Department.id == dept_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if dept is None:
        raise ResourceNotFound(f"Department {dept_id} not found")
    return dept


async def _assert_no_cycle(
    db: AsyncSession, *, dept_id: int, new_parent_id: int | None
) -> None:
    if new_parent_id is None:
        return
    if new_parent_id == dept_id:
        raise ValidationError("Department cannot be its own parent")
    seen: set[int] = {dept_id}
    current: int | None = new_parent_id
    while current is not None:
        if current in seen:
            raise ValidationError("Department parent chain would create a cycle")
        seen.add(current)
        row = (
            await db.execute(select(Department.parent_id).where(Department.id == current))
        ).scalar_one_or_none()
        if row is None:
            raise ResourceNotFound(f"Parent department {current} not found")
        current = row


async def list_departments(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    status: str | None = None,
    parent_id: int | None = None,
) -> tuple[list[dict], int]:
    query = select(Department)
    count_query = select(func.count()).select_from(Department)

    if keyword:
        pattern = f"%{keyword}%"
        cond = (Department.department_code.ilike(pattern)) | (
            Department.department_name.ilike(pattern)
        )
        query = query.where(cond)
        count_query = count_query.where(cond)
    if status:
        query = query.where(Department.status == status)
        count_query = count_query.where(Department.status == status)
    if parent_id is not None:
        query = query.where(Department.parent_id == parent_id)
        count_query = count_query.where(Department.parent_id == parent_id)

    total = (await db.execute(count_query)).scalar_one()
    stmt = (
        query.order_by(Department.department_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_out(r) for r in rows], total


async def get_department(db: AsyncSession, dept_id: int) -> dict:
    return _to_out(await _load(db, dept_id))


async def department_tree(db: AsyncSession, *, include_disabled: bool = False) -> list[dict]:
    stmt = select(Department).order_by(Department.department_code)
    if not include_disabled:
        stmt = stmt.where(Department.status == "active")
    depts = (await db.execute(stmt)).scalars().all()

    nodes: dict[int, dict] = {
        d.id: {
            "id": d.id,
            "department_code": d.department_code,
            "department_name": d.department_name,
            "status": d.status,
            "children": [],
        }
        for d in depts
    }
    roots: list[dict] = []
    for d in depts:
        node = nodes[d.id]
        if d.parent_id is not None and d.parent_id in nodes:
            nodes[d.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


async def create_department(
    db: AsyncSession,
    payload: DepartmentCreate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    existing = (
        await db.execute(
            select(Department).where(Department.department_code == payload.department_code)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"Department code '{payload.department_code}' already exists"
        )

    if payload.parent_id is not None:
        await _load(db, payload.parent_id)
    if payload.manager_employee_id is not None:
        emp = (
            await db.execute(
                select(Employee.id).where(Employee.id == payload.manager_employee_id)
            )
        ).scalar_one_or_none()
        if emp is None:
            raise ValidationError(
                f"Manager employee {payload.manager_employee_id} not found"
            )

    dept = Department(
        department_code=payload.department_code,
        department_name=payload.department_name,
        parent_id=payload.parent_id,
        manager_employee_id=payload.manager_employee_id,
        status=payload.status,
    )
    db.add(dept)
    await db.flush()

    await audit_service.write_audit(
        db,
        action="department.create",
        resource_type="department",
        resource_id=dept.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_to_out(dept),
    )
    await db.commit()
    return _to_out(await _load(db, dept.id))


async def update_department(
    db: AsyncSession,
    dept_id: int,
    payload: DepartmentUpdate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    dept = await _load(db, dept_id)
    before = _to_out(dept)

    if payload.department_code is not None and payload.department_code != dept.department_code:
        existing = (
            await db.execute(
                select(Department).where(
                    Department.department_code == payload.department_code,
                    Department.id != dept_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(
                f"Department code '{payload.department_code}' already exists"
            )
        dept.department_code = payload.department_code

    if payload.department_name is not None:
        dept.department_name = payload.department_name

    if "parent_id" in payload.model_fields_set:
        await _assert_no_cycle(db, dept_id=dept_id, new_parent_id=payload.parent_id)
        if payload.parent_id is not None:
            await _load(db, payload.parent_id)
        dept.parent_id = payload.parent_id

    if "manager_employee_id" in payload.model_fields_set:
        if payload.manager_employee_id is not None:
            emp = (
                await db.execute(
                    select(Employee.id).where(Employee.id == payload.manager_employee_id)
                )
            ).scalar_one_or_none()
            if emp is None:
                raise ValidationError(
                    f"Manager employee {payload.manager_employee_id} not found"
                )
        dept.manager_employee_id = payload.manager_employee_id

    if payload.status is not None:
        if payload.status == "disabled":
            child = (
                await db.execute(
                    select(func.count()).select_from(Department).where(
                        Department.parent_id == dept_id,
                        Department.status == "active",
                    )
                )
            ).scalar_one()
            if child > 0:
                raise ValidationError(
                    "Cannot disable department with active child departments"
                )
        dept.status = payload.status

    await audit_service.write_audit(
        db,
        action="department.update",
        resource_type="department",
        resource_id=dept.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=before,
        after_data=_to_out(dept),
    )
    await db.commit()
    return _to_out(await _load(db, dept.id))
