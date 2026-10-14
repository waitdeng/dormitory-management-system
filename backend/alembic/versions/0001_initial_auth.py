"""initial auth and audit tables

Revision ID: 0001_initial_auth
Revises:
Create Date: 2025-10-13

M1 migration: sys_users / sys_roles / sys_permissions / mapping tables /
auth_refresh_tokens / audit_logs.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_auth"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sys_users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_sys_users_username"),
    )
    op.create_index("ix_sys_users_username", "sys_users", ["username"])
    op.create_index("ix_sys_users_employee_id", "sys_users", ["employee_id"])
    op.create_index("ix_sys_users_status", "sys_users", ["status"])

    op.create_table(
        "sys_roles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_sys_roles_code"),
    )
    op.create_index("ix_sys_roles_code", "sys_roles", ["code"])

    op.create_table(
        "sys_permissions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_sys_permissions_code"),
    )
    op.create_index("ix_sys_permissions_code", "sys_permissions", ["code"])
    op.create_index("ix_sys_permissions_module", "sys_permissions", ["module"])

    op.create_table(
        "sys_user_roles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        sa.ForeignKeyConstraint(["user_id"], ["sys_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["sys_roles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sys_user_roles_user_id", "sys_user_roles", ["user_id"])
    op.create_index("ix_sys_user_roles_role_id", "sys_user_roles", ["role_id"])

    op.create_table(
        "sys_role_permissions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        sa.ForeignKeyConstraint(["role_id"], ["sys_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["sys_permissions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sys_role_permissions_role_id", "sys_role_permissions", ["role_id"])
    op.create_index(
        "ix_sys_role_permissions_permission_id", "sys_role_permissions", ["permission_id"]
    )

    op.create_table(
        "auth_refresh_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_auth_refresh_tokens_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["sys_users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_auth_refresh_tokens_user_id", "auth_refresh_tokens", ["user_id"])
    op.create_index("ix_auth_refresh_tokens_token_hash", "auth_refresh_tokens", ["token_hash"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("before_data", sa.JSON(), nullable=True),
        sa.Column("after_data", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("auth_refresh_tokens")
    op.drop_table("sys_role_permissions")
    op.drop_table("sys_user_roles")
    op.drop_table("sys_permissions")
    op.drop_table("sys_roles")
    op.drop_table("sys_users")
