"""FastAPI dependencies: DB session, current user, RBAC checks."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthenticationError, PermissionDenied
from app.core.logging import request_id_ctx
from app.core.security import decode_access_token
from app.models.user import SysUser
from app.services import auth_service

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or request_id_ctx.get() or ""


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> SysUser:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing authentication token")
    payload = decode_access_token(credentials.credentials)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid token payload") from exc

    user = await auth_service.get_user_profile(db, user_id)
    if user["status"] != "active":
        raise AuthenticationError("Account is disabled")

    # Re-hydrate a lightweight user object for permission checks
    return _profile_to_user(user)


class CurrentUser:
    """Lightweight principal carrying id, roles and permissions."""

    def __init__(
        self,
        user_id: int,
        username: str,
        display_name: str,
        roles: list[str],
        permissions: list[str],
        employee_id: int | None = None,
    ):
        self.id = user_id
        self.username = username
        self.display_name = display_name
        self.roles = roles
        self.permissions = permissions
        self.employee_id = employee_id

    def has_permission(self, code: str) -> bool:
        return code in self.permissions


def _profile_to_user(profile: dict) -> CurrentUser:
    return CurrentUser(
        user_id=profile["id"],
        username=profile["username"],
        display_name=profile["display_name"],
        roles=profile["roles"],
        permissions=profile["permissions"],
        employee_id=profile.get("employee_id"),
    )


async def get_current_principal(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    return user


def require_permission(code: str):
    """Dependency factory enforcing a single permission code."""

    async def _checker(
        principal: Annotated[CurrentUser, Depends(get_current_principal)],
    ) -> CurrentUser:
        if not principal.has_permission(code):
            raise PermissionDenied(f"Missing permission: {code}")
        return principal

    return _checker


def require_any_permission(*codes: str):
    async def _checker(
        principal: Annotated[CurrentUser, Depends(get_current_principal)],
    ) -> CurrentUser:
        if not any(principal.has_permission(c) for c in codes):
            raise PermissionDenied(f"Missing permission: one of {', '.join(codes)}")
        return principal

    return _checker


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_principal)]
