"""M3 accommodation business tables (spec §5.1 / §5.3).

Tables:
  accommodation_applications — check-in applications with status machine
  bed_reservations           — bed holds; generated-column unique on active rows
  accommodation_records      — occupancy; generated-column unique on active rows
  transfer_records           — in-service moves
  checkout_records           — check-out workflow

Cross-table conflicts (reservation vs occupancy) are NOT enforceable by
generated-column indexes alone and MUST be re-checked under row locks in
services (spec §5.3 / §5.4).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
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


class AccommodationApplication(Base):
    __tablename__ = "accommodation_applications"
    __table_args__ = (
        UniqueConstraint("application_no", name="uq_accommodation_applications_no"),
        UniqueConstraint("idempotency_key", name="uq_accommodation_applications_idem"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    application_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    application_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="new"
    )  # new | recheck | temporary
    requested_checkin_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assigned_bed_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("dorm_beds.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )  # pending|approved|reserved|checked_in|rejected|cancelled|expired
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    processed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )


class BedReservation(Base):
    __tablename__ = "bed_reservations"
    __table_args__ = (
        UniqueConstraint("reservation_no", name="uq_bed_reservations_no"),
        UniqueConstraint("idempotency_key", name="uq_bed_reservations_idem"),
        UniqueConstraint("active_employee_id", name="uq_active_reservation_employee"),
        UniqueConstraint("active_bed_id", name="uq_active_reservation_bed"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reservation_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    application_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("accommodation_applications.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    employee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bed_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dorm_beds.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )  # active|consumed|cancelled|expired
    reserved_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )

    # Generated columns — UNIQUE enforces at most one active reservation per
    # employee / bed inside THIS table (spec §5.3). Cross-table checks stay
    # in the service layer under row locks.
    active_employee_id: Mapped[int | None] = mapped_column(
        BigInteger,
        Computed("CASE WHEN status = 'active' THEN employee_id ELSE NULL END", persisted=True),
        nullable=True,
    )
    active_bed_id: Mapped[int | None] = mapped_column(
        BigInteger,
        Computed("CASE WHEN status = 'active' THEN bed_id ELSE NULL END", persisted=True),
        nullable=True,
    )


class AccommodationRecord(Base):
    __tablename__ = "accommodation_records"
    __table_args__ = (
        UniqueConstraint("active_employee_id", name="uq_active_accommodation_employee"),
        UniqueConstraint("active_bed_id", name="uq_active_accommodation_bed"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bed_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dorm_beds.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("accommodation_applications.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    checkin_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    checkout_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )  # active|ended|voided
    end_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ended_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )

    active_employee_id: Mapped[int | None] = mapped_column(
        BigInteger,
        Computed("CASE WHEN status = 'active' THEN employee_id ELSE NULL END", persisted=True),
        nullable=True,
    )
    active_bed_id: Mapped[int | None] = mapped_column(
        BigInteger,
        Computed("CASE WHEN status = 'active' THEN bed_id ELSE NULL END", persisted=True),
        nullable=True,
    )


class TransferRecord(Base):
    __tablename__ = "transfer_records"
    __table_args__ = (
        UniqueConstraint("transfer_no", name="uq_transfer_records_no"),
        UniqueConstraint("idempotency_key", name="uq_transfer_records_idem"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transfer_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_accommodation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accommodation_records.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_bed_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dorm_beds.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_bed_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dorm_beds.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_reservation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("bed_reservations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    target_accommodation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("accommodation_records.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )  # pending|reserved|completed|cancelled
    requested_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    processed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )


class CheckoutRecord(Base):
    __tablename__ = "checkout_records"
    __table_args__ = (
        UniqueConstraint("checkout_no", name="uq_checkout_records_no"),
        UniqueConstraint("idempotency_key", name="uq_checkout_records_idem"),
        UniqueConstraint("open_accommodation_id", name="uq_open_checkout_accommodation"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    checkout_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    accommodation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accommodation_records.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    checkout_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="normal"
    )  # normal|offboarding|other
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )  # pending|inspection|completed|cancelled
    expected_checkout_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_checkout_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    key_returned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    access_card_returned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    belongings_cleared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    room_inspected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inspection_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(6), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(6), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(6), nullable=False, default=utcnow, onupdate=utcnow
    )

    # At most one open (pending/inspection) checkout per accommodation record.
    open_accommodation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        Computed(
            "CASE WHEN status IN ('pending','inspection') THEN accommodation_id ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )
