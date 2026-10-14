"""M3 accommodation schemas: check-in, reservations, transfers, checkouts."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

APPLICATION_TYPES = {"new", "recheck", "temporary"}
CHECKOUT_TYPES = {"normal", "offboarding", "other"}


class CheckinApplicationCreate(BaseModel):
    employee_id: int
    application_type: str = Field(default="new", max_length=32)
    requested_checkin_date: date | None = None
    reason: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=128)


class CheckinReserveRequest(BaseModel):
    bed_id: int
    expires_at: datetime | None = None


class CheckinConfirmRequest(BaseModel):
    checkin_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CheckinRejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class CheckinCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class TransferCreate(BaseModel):
    employee_id: int
    target_bed_id: int
    reason: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=128)


class TransferReserveRequest(BaseModel):
    target_bed_id: int | None = None


class TransferCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class CheckoutCreate(BaseModel):
    employee_id: int
    checkout_type: str = Field(default="normal", max_length=32)
    reason: str | None = Field(default=None, max_length=2000)
    expected_checkout_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=128)


class CheckoutInspectionRequest(BaseModel):
    key_returned: bool | None = None
    access_card_returned: bool | None = None
    belongings_cleared: bool | None = None
    room_inspected: bool | None = None
    inspection_notes: str | None = Field(default=None, max_length=2000)


class CheckoutCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
