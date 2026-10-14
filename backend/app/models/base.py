"""Shared ORM base and timestamp mixins."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

__all__ = ["Base", "TimestampMixin", "utcnow"]


def utcnow() -> datetime:
    """Timezone-aware UTC now. Stored as DATETIME(6) in MySQL."""
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    """created_at / updated_at for business tables."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(6),
        nullable=False,
        default=utcnow,
        server_default=None,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=None,
    )


class BigIntPKMixin:
    """BIGINT UNSIGNED primary key."""

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(BigInteger(), "mysql"),
        primary_key=True,
        autoincrement=True,
    )
