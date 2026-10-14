"""Employee schemas (spec §5.1 / §6.2)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

GENDER_VALUES = {"male", "female", "other"}
# Spec §4.3: pending → active → offboarding → terminated. Legacy values kept.
EMPLOYMENT_STATUS_VALUES = {
    "pending",
    "active",
    "probation",
    "offboarding",
    "terminated",
    "resigned",
    "suspended",
}
EMPLOYMENT_TYPE_VALUES = {"full_time", "part_time", "contract", "intern", "outsourced"}
SHIFT_VALUES = {"day", "night", "rotating", "none"}


class EmployeeBase(BaseModel):
    employee_no: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=1, max_length=128)
    gender: str | None = None
    department_id: int | None = None
    position: str | None = Field(default=None, max_length=128)
    employment_type: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    join_date: date | None = None
    termination_date: date | None = None
    employment_status: str = Field(default="active")
    accommodation_required: bool = True
    shift_type: str | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        if v is not None and v not in GENDER_VALUES:
            raise ValueError(f"gender must be one of {sorted(GENDER_VALUES)}")
        return v

    @field_validator("employment_status")
    @classmethod
    def validate_employment_status(cls, v: str) -> str:
        if v not in EMPLOYMENT_STATUS_VALUES:
            raise ValueError(f"employment_status must be one of {sorted(EMPLOYMENT_STATUS_VALUES)}")
        return v

    @field_validator("employment_type")
    @classmethod
    def validate_employment_type(cls, v: str | None) -> str | None:
        if v is not None and v not in EMPLOYMENT_TYPE_VALUES:
            raise ValueError(f"employment_type must be one of {sorted(EMPLOYMENT_TYPE_VALUES)}")
        return v

    @field_validator("shift_type")
    @classmethod
    def validate_shift_type(cls, v: str | None) -> str | None:
        if v is not None and v not in SHIFT_VALUES:
            raise ValueError(f"shift_type must be one of {sorted(SHIFT_VALUES)}")
        return v


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    employee_no: str | None = Field(default=None, min_length=1, max_length=64)
    full_name: str | None = Field(default=None, min_length=1, max_length=128)
    gender: str | None = None
    department_id: int | None = None
    position: str | None = Field(default=None, max_length=128)
    employment_type: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    join_date: date | None = None
    termination_date: date | None = None
    employment_status: str | None = None
    accommodation_required: bool | None = None
    shift_type: str | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        if v is not None and v not in GENDER_VALUES:
            raise ValueError(f"gender must be one of {sorted(GENDER_VALUES)}")
        return v

    @field_validator("employment_status")
    @classmethod
    def validate_employment_status(cls, v: str | None) -> str | None:
        if v is not None and v not in EMPLOYMENT_STATUS_VALUES:
            raise ValueError(f"employment_status must be one of {sorted(EMPLOYMENT_STATUS_VALUES)}")
        return v

    @field_validator("employment_type")
    @classmethod
    def validate_employment_type(cls, v: str | None) -> str | None:
        if v is not None and v not in EMPLOYMENT_TYPE_VALUES:
            raise ValueError(f"employment_type must be one of {sorted(EMPLOYMENT_TYPE_VALUES)}")
        return v

    @field_validator("shift_type")
    @classmethod
    def validate_shift_type(cls, v: str | None) -> str | None:
        if v is not None and v not in SHIFT_VALUES:
            raise ValueError(f"shift_type must be one of {sorted(SHIFT_VALUES)}")
        return v


class EmployeeOut(BaseModel):
    id: int
    employee_no: str
    full_name: str
    gender: str | None = None
    department_id: int | None = None
    department_code: str | None = None
    department_name: str | None = None
    position: str | None = None
    employment_type: str | None = None
    phone: str | None = None
    join_date: date | None = None
    termination_date: date | None = None
    employment_status: str
    accommodation_required: bool
    shift_type: str | None = None
    notes: str | None = None
    # Derived placeholders — real occupancy arrives with M3 accommodation tables.
    accommodation_status: str = "not_in_dorm"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class EmployeeImportRowResult(BaseModel):
    row_no: int
    action: str  # create | update | skip | error
    employee_no: str | None = None
    full_name: str | None = None
    message: str | None = None
    data: dict | None = None


class EmployeeImportPreviewOut(BaseModel):
    import_job_id: int
    filename: str
    total_rows: int
    create_count: int
    update_count: int
    skip_count: int
    error_count: int
    rows: list[EmployeeImportRowResult]


class EmployeeImportCommitOut(BaseModel):
    import_job_id: int
    status: str
    total_rows: int
    success_rows: int
    failed_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    errors: list[EmployeeImportRowResult] = Field(default_factory=list)


class ImportJobOut(BaseModel):
    id: int
    import_type: str
    filename: str
    file_hash: str
    status: str
    total_rows: int
    success_rows: int
    failed_rows: int
    created_by: int | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
