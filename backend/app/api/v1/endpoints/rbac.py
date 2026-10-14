"""Roles and permissions dictionary endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbSession
from app.schemas.user import PermissionOut, RoleOut
from app.services import user_service

router = APIRouter(tags=["rbac"])


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(db: DbSession, _user: CurrentUserDep) -> list[RoleOut]:
    rows = await user_service.list_roles(db)
    return [RoleOut(**r) for r in rows]


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(db: DbSession, _user: CurrentUserDep) -> list[PermissionOut]:
    rows = await user_service.list_permissions(db)
    return [PermissionOut(**p) for p in rows]
