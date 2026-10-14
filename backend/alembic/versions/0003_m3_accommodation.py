"""M3 accommodation business tables

Revision ID: 0003_m3_accommodation
Revises: 0002_m2_master_data
Create Date: 2026-10-13

M3 migration (spec §5.1 / §5.3, AGENTS.md M3 scope):
  accommodation_applications, bed_reservations, accommodation_records,
  transfer_records, checkout_records.

Generated-column UNIQUE indexes enforce single active occupancy/reservation
inside each table. Cross-table conflicts are validated in services under
row locks (spec §5.3 note).

Does NOT create M4 tables (employee_status_events, workflow_todos).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_m3_accommodation"
down_revision: Union[str, None] = "0002_m2_master_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- accommodation_applications ----
    op.create_table(
        "accommodation_applications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("application_no", sa.String(length=64), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("application_type", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("requested_checkin_date", sa.Date(), nullable=True),
        sa.Column("assigned_bed_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_by", sa.BigInteger(), nullable=True),
        sa.Column("processed_by", sa.BigInteger(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_no", name="uq_accommodation_applications_no"),
        sa.UniqueConstraint("idempotency_key", name="uq_accommodation_applications_idem"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_bed_id"], ["dorm_beds.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_accommodation_applications_application_no",
        "accommodation_applications",
        ["application_no"],
    )
    op.create_index(
        "ix_accommodation_applications_employee_id",
        "accommodation_applications",
        ["employee_id"],
    )
    op.create_index(
        "ix_accommodation_applications_assigned_bed_id",
        "accommodation_applications",
        ["assigned_bed_id"],
    )
    op.create_index(
        "ix_accommodation_applications_status", "accommodation_applications", ["status"]
    )

    # ---- bed_reservations ----
    op.create_table(
        "bed_reservations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("reservation_no", sa.String(length=64), nullable=False),
        sa.Column("application_id", sa.BigInteger(), nullable=True),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("bed_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("reserved_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("release_reason", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column(
            "active_employee_id",
            sa.BigInteger(),
            sa.Computed(
                "CASE WHEN status = 'active' THEN employee_id ELSE NULL END", persisted=True
            ),
            nullable=True,
        ),
        sa.Column(
            "active_bed_id",
            sa.BigInteger(),
            sa.Computed("CASE WHEN status = 'active' THEN bed_id ELSE NULL END", persisted=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reservation_no", name="uq_bed_reservations_no"),
        sa.UniqueConstraint("idempotency_key", name="uq_bed_reservations_idem"),
        sa.UniqueConstraint("active_employee_id", name="uq_active_reservation_employee"),
        sa.UniqueConstraint("active_bed_id", name="uq_active_reservation_bed"),
        sa.ForeignKeyConstraint(
            ["application_id"], ["accommodation_applications.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bed_id"], ["dorm_beds.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_bed_reservations_reservation_no", "bed_reservations", ["reservation_no"])
    op.create_index("ix_bed_reservations_application_id", "bed_reservations", ["application_id"])
    op.create_index("ix_bed_reservations_employee_id", "bed_reservations", ["employee_id"])
    op.create_index("ix_bed_reservations_bed_id", "bed_reservations", ["bed_id"])
    op.create_index("ix_bed_reservations_status", "bed_reservations", ["status"])

    # ---- accommodation_records ----
    op.create_table(
        "accommodation_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("bed_id", sa.BigInteger(), nullable=False),
        sa.Column("application_id", sa.BigInteger(), nullable=True),
        sa.Column("checkin_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("checkout_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("end_reason", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("ended_by", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column(
            "active_employee_id",
            sa.BigInteger(),
            sa.Computed(
                "CASE WHEN status = 'active' THEN employee_id ELSE NULL END", persisted=True
            ),
            nullable=True,
        ),
        sa.Column(
            "active_bed_id",
            sa.BigInteger(),
            sa.Computed("CASE WHEN status = 'active' THEN bed_id ELSE NULL END", persisted=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("active_employee_id", name="uq_active_accommodation_employee"),
        sa.UniqueConstraint("active_bed_id", name="uq_active_accommodation_bed"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bed_id"], ["dorm_beds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["application_id"], ["accommodation_applications.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_accommodation_records_employee_id", "accommodation_records", ["employee_id"])
    op.create_index("ix_accommodation_records_bed_id", "accommodation_records", ["bed_id"])
    op.create_index(
        "ix_accommodation_records_application_id", "accommodation_records", ["application_id"]
    )
    op.create_index("ix_accommodation_records_status", "accommodation_records", ["status"])
    op.create_index(
        "ix_accommodation_records_checkin_at", "accommodation_records", ["checkin_at"]
    )
    op.create_check_constraint(
        "chk_accommodation_dates",
        "accommodation_records",
        "(status = 'active' AND checkout_at IS NULL) OR "
        "(status = 'ended' AND checkout_at IS NOT NULL AND checkout_at >= checkin_at) OR "
        "(status = 'voided')",
    )

    # ---- transfer_records ----
    op.create_table(
        "transfer_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("transfer_no", sa.String(length=64), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("source_accommodation_id", sa.BigInteger(), nullable=False),
        sa.Column("source_bed_id", sa.BigInteger(), nullable=False),
        sa.Column("target_bed_id", sa.BigInteger(), nullable=False),
        sa.Column("target_reservation_id", sa.BigInteger(), nullable=True),
        sa.Column("target_accommodation_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("processed_by", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transfer_no", name="uq_transfer_records_no"),
        sa.UniqueConstraint("idempotency_key", name="uq_transfer_records_idem"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_accommodation_id"], ["accommodation_records.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_bed_id"], ["dorm_beds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_bed_id"], ["dorm_beds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["target_reservation_id"], ["bed_reservations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_accommodation_id"], ["accommodation_records.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_transfer_records_transfer_no", "transfer_records", ["transfer_no"])
    op.create_index("ix_transfer_records_employee_id", "transfer_records", ["employee_id"])
    op.create_index(
        "ix_transfer_records_source_accommodation_id",
        "transfer_records",
        ["source_accommodation_id"],
    )
    op.create_index("ix_transfer_records_source_bed_id", "transfer_records", ["source_bed_id"])
    op.create_index("ix_transfer_records_target_bed_id", "transfer_records", ["target_bed_id"])
    op.create_index("ix_transfer_records_status", "transfer_records", ["status"])
    op.create_check_constraint(
        "chk_transfer_beds_different",
        "transfer_records",
        "source_bed_id <> target_bed_id",
    )

    # ---- checkout_records ----
    op.create_table(
        "checkout_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("checkout_no", sa.String(length=64), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("accommodation_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "checkout_type", sa.String(length=32), nullable=False, server_default="normal"
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("expected_checkout_date", sa.Date(), nullable=True),
        sa.Column("actual_checkout_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("key_returned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("access_card_returned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("belongings_cleared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("room_inspected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("inspection_notes", sa.Text(), nullable=True),
        sa.Column("processed_by", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column(
            "open_accommodation_id",
            sa.BigInteger(),
            sa.Computed(
                "CASE WHEN status IN ('pending','inspection') THEN accommodation_id ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkout_no", name="uq_checkout_records_no"),
        sa.UniqueConstraint("idempotency_key", name="uq_checkout_records_idem"),
        sa.UniqueConstraint("open_accommodation_id", name="uq_open_checkout_accommodation"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["accommodation_id"], ["accommodation_records.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_checkout_records_checkout_no", "checkout_records", ["checkout_no"])
    op.create_index("ix_checkout_records_employee_id", "checkout_records", ["employee_id"])
    op.create_index(
        "ix_checkout_records_accommodation_id", "checkout_records", ["accommodation_id"]
    )
    op.create_index("ix_checkout_records_status", "checkout_records", ["status"])


def downgrade() -> None:
    op.drop_table("checkout_records")
    op.drop_table("transfer_records")
    op.drop_table("accommodation_records")
    op.drop_table("bed_reservations")
    op.drop_table("accommodation_applications")
