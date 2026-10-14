"""Shared response envelopes."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageEnvelope(BaseModel, Generic[T]):
    """Standard list envelope (spec §6)."""

    items: list[T]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class StatusMessage(BaseModel):
    message: str
    data: dict[str, Any] | None = None
