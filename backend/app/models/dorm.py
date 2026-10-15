"""Dormitory resource hierarchy (spec §5.1 / §5.5).

Area 1:N Building 1:N Floor 1:N Room 1:N Bed.
Bed.operational_status is only active/maintenance/disabled — occupancy and
reservations are computed from M3 relation tables, never stored here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import utcnow


class DormArea(Base):
    __tablename__ = "dorm_areas"
    __table_args__ = (UniqueConstraint("area_code", name="uq_dorm_areas_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    area_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    area_name: Mapped[str] = mapped_column(String(128), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )


class DormBuilding(Base):
    __tablename__ = "dorm_buildings"
    __table_args__ = (
        UniqueConstraint("area_id", "building_code", name="uq_dorm_buildings_area_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    area_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dorm_areas.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    building_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    building_name: Mapped[str] = mapped_column(String(128), nullable=False)
    total_floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="any")
    manager_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )


class DormFloor(Base):
    __tablename__ = "dorm_floors"
    __table_args__ = (
        UniqueConstraint("building_id", "floor_no", name="uq_dorm_floors_building_no"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    building_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dorm_buildings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    floor_no: Mapped[int] = mapped_column(Integer, nullable=False)
    floor_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gender_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="any")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )


class DormRoom(Base):
    __tablename__ = "dorm_rooms"
    __table_args__ = (
        UniqueConstraint("floor_id", "room_no", name="uq_dorm_rooms_floor_no"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    floor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dorm_floors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    room_no: Mapped[str] = mapped_column(String(32), nullable=False)
    room_type: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    # FEAT-008: encrypted door access code; plaintext never stored.
    access_code_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gender_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="any")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )


class DormRoomType(Base):
    """FEAT-002: custom room type catalogue. Changing type name must NOT
    auto-change existing room capacity — capacity stays a per-room field."""

    __tablename__ = "dorm_room_types"
    __table_args__ = (UniqueConstraint("type_code", name="uq_dorm_room_types_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type_code: Mapped[str] = mapped_column(String(32), nullable=False)
    type_name: Mapped[str] = mapped_column(String(64), nullable=False)
    default_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )


class DormBed(Base):
    __tablename__ = "dorm_beds"
    __table_args__ = (UniqueConstraint("room_id", "bed_no", name="uq_dorm_beds_room_no"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dorm_rooms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bed_no: Mapped[str] = mapped_column(String(32), nullable=False)
    operational_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )
