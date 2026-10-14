"""Authentication endpoints: login, logout, refresh, me, permissions."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUserDep, DbSession, get_request_id
from app.core.config import settings
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    result = await auth_service.login(
        db,
        username=payload.username,
        password=payload.password,
        request_id=get_request_id(request),
        ip_address=_client_ip(request),
    )
    return TokenResponse(**result)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request, db: DbSession) -> TokenResponse:
    result = await auth_service.refresh_tokens(
        db,
        refresh_token=payload.refresh_token,
        request_id=get_request_id(request),
    )
    return TokenResponse(**result)


@router.post("/logout")
async def logout(
    payload: LogoutRequest,
    request: Request,
    db: DbSession,
    principal: CurrentUserDep,
) -> dict:
    await auth_service.logout(
        db,
        user_id=principal.id,
        refresh_token=payload.refresh_token,
        request_id=get_request_id(request),
    )
    return {"message": "Logged out"}


@router.get("/me", response_model=MeResponse)
async def me(principal: CurrentUserDep, db: DbSession) -> MeResponse:
    profile = await auth_service.get_user_profile(db, principal.id)
    return MeResponse(**profile)


@router.get("/permissions")
async def my_permissions(principal: CurrentUserDep) -> dict:
    return {
        "roles": principal.roles,
        "permissions": principal.permissions,
    }


@router.get("/token-lifetime")
async def token_lifetime(_user: CurrentUserDep) -> dict:
    """Token lifetime config. Requires authentication — not a public info endpoint."""
    return {
        "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "refresh_token_expire_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
    }
