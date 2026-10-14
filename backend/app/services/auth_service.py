"""Auth service: login, token refresh/revocation, me/permissions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token_value,
    fingerprint_refresh_token,
    verify_password,
)
from app.models.base import utcnow
from app.models.rbac import SysRole
from app.models.user import AuthRefreshToken, SysUser
from app.services import audit_service


async def _load_user_with_roles(db: AsyncSession, user_id: int) -> SysUser | None:
    stmt = (
        select(SysUser)
        .where(SysUser.id == user_id)
        .options(selectinload(SysUser.roles).selectinload(SysRole.permissions))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def collect_permissions(user: SysUser) -> list[str]:
    codes: set[str] = set()
    for role in user.roles:
        if role.status != "active":
            continue
        for perm in role.permissions:
            codes.add(perm.code)
    return sorted(codes)


def collect_roles(user: SysUser) -> list[str]:
    return sorted(r.code for r in user.roles if r.status == "active")


async def authenticate_user(db: AsyncSession, username: str, password: str) -> SysUser:
    stmt = (
        select(SysUser)
        .where(SysUser.username == username)
        .options(selectinload(SysUser.roles).selectinload(SysRole.permissions))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid username or password")
    if user.status != "active":
        raise AuthenticationError("Account is disabled")
    return user


async def login(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> dict:
    user = await authenticate_user(db, username, password)
    user.last_login_at = utcnow()

    access = create_access_token(
        str(user.id),
        username=user.username,
        extra_claims={"roles": collect_roles(user)},
    )
    raw_refresh, token_hash, expires_at = create_refresh_token_value()
    db.add(
        AuthRefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    await audit_service.write_audit(
        db,
        action="auth.login",
        resource_type="sys_user",
        resource_id=user.id,
        actor_user_id=user.id,
        request_id=request_id,
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(user)

    return {
        "access_token": access,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "permissions": collect_permissions(user),
        "roles": collect_roles(user),
    }


async def refresh_tokens(
    db: AsyncSession,
    *,
    refresh_token: str,
    request_id: str | None = None,
) -> dict:
    token_hash = fingerprint_refresh_token(refresh_token)
    stmt = select(AuthRefreshToken).where(AuthRefreshToken.token_hash == token_hash)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    now = utcnow()
    if record is None or record.revoked_at is not None or record.expires_at < now:
        raise AuthenticationError("Invalid refresh token")

    user = await _load_user_with_roles(db, record.user_id)
    if user is None or user.status != "active":
        raise AuthenticationError("Account is not active")

    # Rotate: revoke old, issue new
    record.revoked_at = now
    access = create_access_token(
        str(user.id),
        username=user.username,
        extra_claims={"roles": collect_roles(user)},
    )
    raw_refresh, new_hash, expires_at = create_refresh_token_value()
    db.add(AuthRefreshToken(user_id=user.id, token_hash=new_hash, expires_at=expires_at))
    await audit_service.write_audit(
        db,
        action="auth.refresh",
        resource_type="sys_user",
        resource_id=user.id,
        actor_user_id=user.id,
        request_id=request_id,
    )
    await db.commit()

    return {
        "access_token": access,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "permissions": collect_permissions(user),
        "roles": collect_roles(user),
    }


async def logout(
    db: AsyncSession,
    *,
    user_id: int,
    refresh_token: str | None = None,
    request_id: str | None = None,
) -> None:
    if refresh_token:
        token_hash = fingerprint_refresh_token(refresh_token)
        stmt = select(AuthRefreshToken).where(AuthRefreshToken.token_hash == token_hash)
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()
        if record and record.user_id == user_id and record.revoked_at is None:
            record.revoked_at = utcnow()
    else:
        # Revoke all active refresh tokens for the user
        stmt = select(AuthRefreshToken).where(
            AuthRefreshToken.user_id == user_id,
            AuthRefreshToken.revoked_at.is_(None),
        )
        result = await db.execute(stmt)
        for record in result.scalars().all():
            record.revoked_at = utcnow()

    await audit_service.write_audit(
        db,
        action="auth.logout",
        resource_type="sys_user",
        resource_id=user_id,
        actor_user_id=user_id,
        request_id=request_id,
    )
    await db.commit()


async def get_user_profile(db: AsyncSession, user_id: int) -> dict:
    user = await _load_user_with_roles(db, user_id)
    if user is None:
        raise AuthenticationError("User not found")
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "employee_id": user.employee_id,
        "status": user.status,
        "roles": collect_roles(user),
        "permissions": collect_permissions(user),
        "last_login_at": user.last_login_at,
    }


async def revoke_all_user_tokens(db: AsyncSession, user_id: int) -> None:
    """Used when an account is disabled."""
    stmt = select(AuthRefreshToken).where(
        AuthRefreshToken.user_id == user_id,
        AuthRefreshToken.revoked_at.is_(None),
    )
    result = await db.execute(stmt)
    for record in result.scalars().all():
        record.revoked_at = utcnow()
    await db.commit()
