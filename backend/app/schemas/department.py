"""Department schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DepartmentBase(BaseModel):
    department_code: str = Field(min_length=1, max_length=64)
    department_name: str = Field(min_length=1, max_length=128)
    parent_id: int | None = None
    manager_employee_id: int | None = None
    status: str = Field(default="active")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in {"active", "disabled"}:
            raise ValueError("status must be active or disabled")
        return v


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    department_code: str | None = Field(default=None, min_length=1, max_length=64)
    department_name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: int | None = None
    manager_employee_id: int | None = None
    status: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in {"active", "disabled"}:
            raise ValueError("status must be active or disabled")
        return v


class DepartmentOut(BaseModel):
    id: int
    department_code: str
    department_name: str
    parent_id: int | None = None
    manager_employee_id: int | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DepartmentTreeNode(BaseModel):
    id: int
    department_code: str
    department_name: str
    status: str
    children: list[DepartmentTreeNode] = Field(default_factory=list)
