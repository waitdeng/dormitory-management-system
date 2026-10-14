"""M5: department data-scope assignments for scoped roles

Revision ID: 0005_m5_reports_scope
Revises: 0004_m4_workflow
Create Date: 2026-10-13

M5 migration (AGENTS.md M5 P0 — 部门数据权限隔离):
  sys_user_departments — explicit user ↔ department data-scope rows.

Does NOT modify M1–M4 tables. Rollback drops only this table.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_m5_reports_scope"
down_revision: Union[str, None] = "0004_m4_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sys_user_departments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "department_id", name="uq_sys_user_departments"),
        sa.ForeignKeyConstraint(["user_id"], ["sys_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sys_user_departments_user_id", "sys_user_departments", ["user_id"])
    op.create_index(
        "ix_sys_user_departments_department_id", "sys_user_departments", ["department_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_sys_user_departments_department_id", table_name="sys_user_departments")
    op.drop_index("ix_sys_user_departments_user_id", table_name="sys_user_departments")
    op.drop_table("sys_user_departments")
