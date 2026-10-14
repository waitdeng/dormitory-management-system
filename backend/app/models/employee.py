"""Employee master data (spec §5.1).

Matched by employee_no (UNIQUE) per AGENTS.md §5. Department FK is RESTRICT —
departments referenced by employees must be disabled, not deleted.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import utcnow


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("employee_no", name="uq_employees_employee_no"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    department_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    position: Mapped[str | None] = mapped_column(String(128), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    join_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    employment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )
    accommodation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    shift_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )
