"""Department management endpoints (M2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import CurrentUser, DbSession, get_request_id, require_permission
from app.core.permissions import PERM_EMPLOYEE_CREATE, PERM_EMPLOYEE_UPDATE, PERM_EMPLOYEE_VIEW
from app.schemas.common import PageEnvelope
from app.schemas.department import (
    DepartmentCreate,
    DepartmentOut,
    DepartmentTreeNode,
    DepartmentUpdate,
)
from app.services import department_service

router = APIRouter(prefix="/departments", tags=["departments"])

ViewDept = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_VIEW))]
CreateDept = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_CREATE))]
UpdateDept = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_UPDATE))]


@router.get("", response_model=PageEnvelope[DepartmentOut])
async def list_departments(
    db: DbSession,
    _guard: ViewDept,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    status: str | None = Query(None, max_length=16),
    parent_id: int | None = Query(None, ge=1),
) -> PageEnvelope[DepartmentOut]:
    items, total = await department_service.list_departments(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status,
        parent_id=parent_id,
    )
    return PageEnvelope[DepartmentOut](
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/tree", response_model=list[DepartmentTreeNode])
async def department_tree(
    db: DbSession,
    _guard: ViewDept,
    include_disabled: bool = Query(False),
) -> list[DepartmentTreeNode]:
    return await department_service.department_tree(db, include_disabled=include_disabled)


@router.get("/{department_id}", response_model=DepartmentOut)
async def get_department(
    department_id: int,
    db: DbSession,
    _guard: ViewDept,
) -> DepartmentOut:
    return DepartmentOut(**await department_service.get_department(db, department_id))


@router.post("", response_model=DepartmentOut, status_code=201)
async def create_department(
    payload: DepartmentCreate,
    request: Request,
    db: DbSession,
    guard: CreateDept,
) -> DepartmentOut:
    data = await department_service.create_department(
        db,
        payload,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return DepartmentOut(**data)


@router.patch("/{department_id}", response_model=DepartmentOut)
async def update_department(
    department_id: int,
    payload: DepartmentUpdate,
    request: Request,
    db: DbSession,
    guard: UpdateDept,
) -> DepartmentOut:
    data = await department_service.update_department(
        db,
        department_id,
        payload,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return DepartmentOut(**data)
