"""Role and permission models (spec §5.1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import utcnow


class SysRole(Base):
    __tablename__ = "sys_roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )

    permissions: Mapped[list[SysPermission]] = relationship(
        "SysPermission",
        secondary="sys_role_permissions",
        back_populates="roles",
        lazy="selectin",
    )
    users: Mapped[list[SysUser]] = relationship(
        "SysUser",
        secondary="sys_user_roles",
        back_populates="roles",
        lazy="selectin",
    )


class SysPermission(Base):
    __tablename__ = "sys_permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )

    roles: Mapped[list[SysRole]] = relationship(
        "SysRole",
        secondary="sys_role_permissions",
        back_populates="permissions",
        lazy="selectin",
    )


class SysRolePermission(Base):
    __tablename__ = "sys_role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_permissions.id", ondelete="CASCADE"), nullable=False, index=True
    )


# Type-only import to satisfy annotations without runtime circularity
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    from app.models.user import SysUser
