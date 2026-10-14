"""Explicit department data-scope assignments for backend accounts (M5).

Scope resolution (see app.services.data_scope):
  - super_admin / hr → all departments
  - other roles → departments from this table ∪ departments managed via
    departments.manager_employee_id (and their descendants)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import utcnow


class SysUserDepartment(Base):
    __tablename__ = "sys_user_departments"
    __table_args__ = (
        UniqueConstraint("user_id", "department_id", name="uq_sys_user_departments"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sys_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
