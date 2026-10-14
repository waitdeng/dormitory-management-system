"""M4 workflow tables (spec §5.1 / AGENTS.md M4).

Tables:
  employee_status_events — HR status transitions with source idempotency
  workflow_todos         — admin to-dos (checkout after offboarding, etc.)
  workflow_alerts        — abnormal-condition alerts (terminated still housed, …)
  notifications          — in-app notices tied to business events

Generated-column UNIQUE indexes keep at most one pending to-do per
(todo_type, business_type, business_id) and at most one active alert per
fingerprint. Repeated scans / events are therefore idempotent at the DB level.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import utcnow


class EmployeeStatusEvent(Base):
    """HR employment status change events (spec §4.5 / BR-006).

    source + source_event_id is the idempotency key so repeated submissions of
    the same offboarding / termination event do not duplicate side-effects.
    """

    __tablename__ = "employee_status_events"
    __table_args__ = (
        UniqueConstraint("source", "source_event_id", name="uq_employee_status_events_src"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # offboarding|terminated|reactivated|status_change
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="api"
    )  # api|scan|import|system
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, index=True
    )


class WorkflowTodo(Base):
    """Admin to-dos (spec §5.1 workflow_todos / §6.7)."""

    __tablename__ = "workflow_todos"
    __table_args__ = (
        UniqueConstraint("open_business_key", name="uq_workflow_todos_open_business"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    todo_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # checkout_offboarding|overdue_checkin|reservation_release|manual
    business_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # checkout|accommodation|reservation|employee|application
    business_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    assignee_role: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    assignee_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )  # pending|completed|cancelled
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="normal"
    )  # low|normal|high|urgent
    due_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    completed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )

    # At most one pending to-do per business object.
    open_business_key: Mapped[str | None] = mapped_column(
        String(191),
        Computed(
            "CASE WHEN status = 'pending' "
            "THEN CONCAT(todo_type, ':', business_type, ':', "
            "COALESCE(CAST(business_id AS CHAR), '0')) ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )


class WorkflowAlert(Base):
    """Abnormal-condition alerts (spec §10 异常预警 / AGENTS.md M4)."""

    __tablename__ = "workflow_alerts"
    __table_args__ = (
        UniqueConstraint("active_fingerprint", name="uq_workflow_alerts_active_fp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default="warning"
    )  # info|warning|critical
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    bed_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("dorm_beds.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    accommodation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    business_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    business_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )  # active|resolved
    fingerprint: Mapped[str] = mapped_column(String(191), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resolve_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )

    active_fingerprint: Mapped[str | None] = mapped_column(
        String(191),
        Computed("CASE WHEN status = 'active' THEN fingerprint ELSE NULL END", persisted=True),
        nullable=True,
    )


class Notification(Base):
    """In-app notifications for business events (AGENTS.md M4)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("sys_users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    role_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    business_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, index=True
    )
