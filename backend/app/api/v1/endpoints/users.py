"""User account management endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import CurrentUser, DbSession, get_request_id, require_permission
from app.core.permissions import PERM_USER_MANAGE
from app.schemas.common import PageEnvelope
from app.schemas.user import (
    UserCreate,
    UserDepartmentsUpdate,
    UserOut,
    UserRolesUpdate,
    UserUpdate,
)
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])

ManageUser = Annotated[CurrentUser, Depends(require_permission(PERM_USER_MANAGE))]


@router.get("", response_model=PageEnvelope[UserOut])
async def list_users(
    db: DbSession,
    _guard: ManageUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    status: str | None = Query(None, max_length=16),
) -> PageEnvelope[UserOut]:
    items, total = await user_service.list_users(
        db, page=page, page_size=page_size, keyword=keyword, status=status
    )
    return PageEnvelope[UserOut](items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    payload: UserCreate,
    request: Request,
    db: DbSession,
    guard: ManageUser,
) -> UserOut:
    data = await user_service.create_user(
        db,
        payload,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return UserOut(**data)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: DbSession,
    guard: ManageUser,
) -> UserOut:
    data = await user_service.update_user(
        db,
        user_id,
        payload,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return UserOut(**data)


@router.put("/{user_id}/roles", response_model=UserOut)
async def set_user_roles(
    user_id: int,
    payload: UserRolesUpdate,
    request: Request,
    db: DbSession,
    guard: ManageUser,
) -> UserOut:
    data = await user_service.set_user_roles(
        db,
        user_id,
        payload,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return UserOut(**data)


@router.put("/{user_id}/departments", response_model=UserOut)
async def set_user_departments(
    user_id: int,
    payload: UserDepartmentsUpdate,
    request: Request,
    db: DbSession,
    guard: ManageUser,
) -> UserOut:
    data = await user_service.set_user_departments(
        db,
        user_id,
        payload.department_ids,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return UserOut(**data)
