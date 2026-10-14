"""User / role / permission schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    employee_id: int | None = None
    status: str = Field(default="active")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in {"active", "disabled"}:
            raise ValueError("status must be active or disabled")
        return v


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    role_codes: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    employee_id: int | None = None
    status: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in {"active", "disabled"}:
            raise ValueError("status must be active or disabled")
        return v


class UserRolesUpdate(BaseModel):
    role_codes: list[str] = Field(default_factory=list)


class RoleOut(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    status: str
    permissions: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PermissionOut(BaseModel):
    id: int
    code: str
    name: str
    module: str
    description: str | None = None

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    employee_id: int | None = None
    status: str
    roles: list[str] = Field(default_factory=list)
    department_ids: list[int] = Field(default_factory=list)
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserDepartmentsUpdate(BaseModel):
    department_ids: list[int] = Field(default_factory=list)
