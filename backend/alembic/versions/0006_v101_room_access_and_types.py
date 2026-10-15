"""V1.0.1: room door access code + room types (FEAT-002/FEAT-008)

Revision ID: 0006_v101_room_access_and_types
Revises: 0005_m5_reports_scope
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_v101_room_access_and_types"
down_revision = "0005_m5_reports_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # FEAT-008: encrypted door access code (nullable for existing rooms)
    op.add_column(
        "dorm_rooms",
        sa.Column("access_code_encrypted", sa.String(length=512), nullable=True),
    )

    # FEAT-002: custom room types catalogue
    op.create_table(
        "dorm_room_types",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("type_code", sa.String(length=32), nullable=False),
        sa.Column("type_name", sa.String(length=64), nullable=False),
        sa.Column("default_capacity", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(6), nullable=False),
        sa.Column("updated_at", sa.DateTime(6), nullable=False),
        sa.UniqueConstraint("type_code", name="uq_dorm_room_types_code"),
    )


def downgrade() -> None:
    op.drop_table("dorm_room_types")
    op.drop_column("dorm_rooms", "access_code_encrypted")
