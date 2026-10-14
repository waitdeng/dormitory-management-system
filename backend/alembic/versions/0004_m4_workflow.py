"""M4 workflow tables: status events, todos, alerts, notifications

Revision ID: 0004_m4_workflow
Revises: 0003_m3_accommodation
Create Date: 2026-10-13

M4 migration (spec §5.1 / AGENTS.md M4 scope):
  employee_status_events, workflow_todos, workflow_alerts, notifications.

Generated-column UNIQUE:
  - workflow_todos.open_business_key — at most one pending to-do per business
  - workflow_alerts.active_fingerprint — at most one active alert per fingerprint
  - employee_status_events (source, source_event_id) — event idempotency

Does NOT modify M1–M3 tables. Rollback drops only these four tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_m4_workflow"
down_revision: Union[str, None] = "0003_m3_accommodation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- employee_status_events ----
    op.create_table(
        "employee_status_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="api"),
        sa.Column("source_event_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_event_id", name="uq_employee_status_events_src"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_employee_status_events_employee_id", "employee_status_events", ["employee_id"]
    )
    op.create_index(
        "ix_employee_status_events_event_type", "employee_status_events", ["event_type"]
    )
    op.create_index(
        "ix_employee_status_events_created_at", "employee_status_events", ["created_at"]
    )

    # ---- workflow_todos ----
    op.create_table(
        "workflow_todos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("todo_type", sa.String(length=64), nullable=False),
        sa.Column("business_type", sa.String(length=32), nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=True),
        sa.Column("employee_id", sa.BigInteger(), nullable=True),
        sa.Column("assignee_role", sa.String(length=64), nullable=True),
        sa.Column("assignee_user_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("due_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("completed_by", sa.BigInteger(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=255), nullable=True),
        sa.Column("source_event_id", sa.String(length=128), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column(
            "open_business_key",
            sa.String(length=191),
            sa.Computed(
                "CASE WHEN status = 'pending' "
                "THEN CONCAT(todo_type, ':', business_type, ':', "
                "COALESCE(CAST(business_id AS CHAR), '0')) ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("open_business_key", name="uq_workflow_todos_open_business"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_workflow_todos_todo_type", "workflow_todos", ["todo_type"])
    op.create_index("ix_workflow_todos_business_type", "workflow_todos", ["business_type"])
    op.create_index("ix_workflow_todos_business_id", "workflow_todos", ["business_id"])
    op.create_index("ix_workflow_todos_employee_id", "workflow_todos", ["employee_id"])
    op.create_index("ix_workflow_todos_assignee_role", "workflow_todos", ["assignee_role"])
    op.create_index("ix_workflow_todos_assignee_user_id", "workflow_todos", ["assignee_user_id"])
    op.create_index("ix_workflow_todos_status", "workflow_todos", ["status"])

    # ---- workflow_alerts ----
    op.create_table(
        "workflow_alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("employee_id", sa.BigInteger(), nullable=True),
        sa.Column("bed_id", sa.BigInteger(), nullable=True),
        sa.Column("accommodation_id", sa.BigInteger(), nullable=True),
        sa.Column("business_type", sa.String(length=32), nullable=True),
        sa.Column("business_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("fingerprint", sa.String(length=191), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolve_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column(
            "active_fingerprint",
            sa.String(length=191),
            sa.Computed(
                "CASE WHEN status = 'active' THEN fingerprint ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("active_fingerprint", name="uq_workflow_alerts_active_fp"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bed_id"], ["dorm_beds.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_workflow_alerts_alert_type", "workflow_alerts", ["alert_type"])
    op.create_index("ix_workflow_alerts_employee_id", "workflow_alerts", ["employee_id"])
    op.create_index("ix_workflow_alerts_bed_id", "workflow_alerts", ["bed_id"])
    op.create_index(
        "ix_workflow_alerts_accommodation_id", "workflow_alerts", ["accommodation_id"]
    )
    op.create_index("ix_workflow_alerts_status", "workflow_alerts", ["status"])

    # ---- notifications ----
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("role_code", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="system"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("business_type", sa.String(length=32), nullable=True),
        sa.Column("business_id", sa.BigInteger(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["sys_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_role_code", "notifications", ["role_code"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("workflow_alerts")
    op.drop_table("workflow_todos")
    op.drop_table("employee_status_events")
