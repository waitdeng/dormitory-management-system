"""Sys user, user-role mapping and refresh token store (spec §5.1 + D-002/D-003)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import utcnow


class SysUser(Base):
    __tablename__ = "sys_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    employee_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )

    roles: Mapped[list[SysRole]] = relationship(
        "SysRole",
        secondary="sys_user_roles",
        back_populates="users",
        lazy="selectin",
    )


class SysUserRole(Base):
    __tablename__ = "sys_user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_roles.id", ondelete="CASCADE"), nullable=False, index=True
    )


class AuthRefreshToken(Base):
    """Revocable refresh tokens. Only hashes are stored (D-002/D-003)."""

    __tablename__ = "auth_refresh_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)


from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    from app.models.rbac import SysRole
