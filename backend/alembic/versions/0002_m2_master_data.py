"""M2 master data: departments, employees, dorm hierarchy, import_jobs

Revision ID: 0002_m2_master_data
Revises: 0001_initial_auth
Create Date: 2026-10-13

M2 migration (spec §5.1, AGENTS.md M2 scope):
  departments, employees,
  dorm_areas, dorm_buildings, dorm_floors, dorm_rooms, dorm_beds,
  import_jobs.

Does NOT create accommodation/reservation/transfer/checkout tables (M3/M4).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision: str = "0002_m2_master_data"
down_revision: Union[str, None] = "0001_initial_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- departments ----
    op.create_table(
        "departments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("department_code", sa.String(length=64), nullable=False),
        sa.Column("department_name", sa.String(length=128), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("manager_employee_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("department_code", name="uq_departments_code"),
        sa.ForeignKeyConstraint(["parent_id"], ["departments.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_departments_department_code", "departments", ["department_code"])
    op.create_index("ix_departments_parent_id", "departments", ["parent_id"])
    op.create_index("ix_departments_manager_employee_id", "departments", ["manager_employee_id"])
    op.create_index("ix_departments_status", "departments", ["status"])

    # ---- employees ----
    op.create_table(
        "employees",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("employee_no", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=128), nullable=False),
        sa.Column("gender", sa.String(length=16), nullable=True),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("position", sa.String(length=128), nullable=True),
        sa.Column("employment_type", sa.String(length=32), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("join_date", sa.Date(), nullable=True),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column(
            "employment_status", sa.String(length=32), nullable=False, server_default="active"
        ),
        sa.Column("accommodation_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("shift_type", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_no", name="uq_employees_employee_no"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_employees_employee_no", "employees", ["employee_no"])
    op.create_index("ix_employees_department_id", "employees", ["department_id"])
    op.create_index("ix_employees_employment_status", "employees", ["employment_status"])
    op.create_index("ix_employees_full_name", "employees", ["full_name"])

    # ---- dorm_areas ----
    op.create_table(
        "dorm_areas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("area_code", sa.String(length=64), nullable=False),
        sa.Column("area_name", sa.String(length=128), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("area_code", name="uq_dorm_areas_code"),
    )
    op.create_index("ix_dorm_areas_area_code", "dorm_areas", ["area_code"])
    op.create_index("ix_dorm_areas_status", "dorm_areas", ["status"])

    # ---- dorm_buildings ----
    op.create_table(
        "dorm_buildings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("area_id", sa.BigInteger(), nullable=False),
        sa.Column("building_code", sa.String(length=64), nullable=False),
        sa.Column("building_name", sa.String(length=128), nullable=False),
        sa.Column("total_floors", sa.Integer(), nullable=True),
        sa.Column("gender_policy", sa.String(length=16), nullable=False, server_default="any"),
        sa.Column("manager_user_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("area_id", "building_code", name="uq_dorm_buildings_area_code"),
        sa.ForeignKeyConstraint(["area_id"], ["dorm_areas.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_dorm_buildings_area_id", "dorm_buildings", ["area_id"])
    op.create_index("ix_dorm_buildings_building_code", "dorm_buildings", ["building_code"])

    # ---- dorm_floors ----
    op.create_table(
        "dorm_floors",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("building_id", sa.BigInteger(), nullable=False),
        sa.Column("floor_no", sa.Integer(), nullable=False),
        sa.Column("floor_name", sa.String(length=64), nullable=True),
        sa.Column("gender_policy", sa.String(length=16), nullable=False, server_default="any"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("building_id", "floor_no", name="uq_dorm_floors_building_no"),
        sa.ForeignKeyConstraint(["building_id"], ["dorm_buildings.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_dorm_floors_building_id", "dorm_floors", ["building_id"])

    # ---- dorm_rooms ----
    op.create_table(
        "dorm_rooms",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("floor_id", sa.BigInteger(), nullable=False),
        sa.Column("room_no", sa.String(length=32), nullable=False),
        sa.Column("room_type", sa.String(length=32), nullable=False, server_default="standard"),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("gender_policy", sa.String(length=16), nullable=False, server_default="any"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("floor_id", "room_no", name="uq_dorm_rooms_floor_no"),
        sa.ForeignKeyConstraint(["floor_id"], ["dorm_floors.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("capacity > 0", name="chk_dorm_rooms_capacity_positive"),
    )
    op.create_index("ix_dorm_rooms_floor_id", "dorm_rooms", ["floor_id"])
    op.create_index("ix_dorm_rooms_status", "dorm_rooms", ["status"])

    # ---- dorm_beds ----
    op.create_table(
        "dorm_beds",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.BigInteger(), nullable=False),
        sa.Column("bed_no", sa.String(length=32), nullable=False),
        sa.Column(
            "operational_status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "bed_no", name="uq_dorm_beds_room_no"),
        sa.ForeignKeyConstraint(["room_id"], ["dorm_rooms.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_dorm_beds_room_id", "dorm_beds", ["room_id"])
    op.create_index("ix_dorm_beds_operational_status", "dorm_beds", ["operational_status"])

    # ---- import_jobs ----
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("import_type", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="previewed"
        ),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_file_path", sa.String(length=512), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=6), nullable=False),
        sa.Column("detail", sa.Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_jobs_import_type", "import_jobs", ["import_type"])
    op.create_index("ix_import_jobs_file_hash", "import_jobs", ["file_hash"])
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])
    op.create_index("ix_import_jobs_created_by", "import_jobs", ["created_by"])


def downgrade() -> None:
    op.drop_table("import_jobs")
    op.drop_table("dorm_beds")
    op.drop_table("dorm_rooms")
    op.drop_table("dorm_floors")
    op.drop_table("dorm_buildings")
    op.drop_table("dorm_areas")
    op.drop_table("employees")
    op.drop_table("departments")
