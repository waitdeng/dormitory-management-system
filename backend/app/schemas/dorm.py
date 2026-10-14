"""Dormitory resource schemas (spec §5.1 / §6.3)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

GENDER_POLICY_VALUES = {"any", "male", "female"}
BED_STATUS_VALUES = {"active", "maintenance", "disabled"}
NODE_STATUS_VALUES = {"active", "disabled"}


def _validate_gender_policy(v: str) -> str:
    if v not in GENDER_POLICY_VALUES:
        raise ValueError(f"gender_policy must be one of {sorted(GENDER_POLICY_VALUES)}")
    return v


def _validate_node_status(v: str) -> str:
    if v not in NODE_STATUS_VALUES:
        raise ValueError("status must be active or disabled")
    return v


class DormAreaBase(BaseModel):
    area_code: str = Field(min_length=1, max_length=64)
    area_name: str = Field(min_length=1, max_length=128)
    address: str | None = Field(default=None, max_length=255)
    status: str = Field(default="active")
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        return _validate_node_status(v)


class DormAreaCreate(DormAreaBase):
    pass


class DormAreaUpdate(BaseModel):
    area_code: str | None = Field(default=None, min_length=1, max_length=64)
    area_name: str | None = Field(default=None, min_length=1, max_length=128)
    address: str | None = Field(default=None, max_length=255)
    status: str | None = None
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_node_status(v)
        return v


class DormAreaOut(BaseModel):
    id: int
    area_code: str
    area_name: str
    address: str | None = None
    status: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class BuildingBase(BaseModel):
    area_id: int
    building_code: str = Field(min_length=1, max_length=64)
    building_name: str = Field(min_length=1, max_length=128)
    total_floors: int | None = Field(default=None, ge=1, le=200)
    gender_policy: str = Field(default="any")
    manager_user_id: int | None = None
    status: str = Field(default="active")
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("gender_policy")
    @classmethod
    def validate_gender_policy(cls, v: str) -> str:
        return _validate_gender_policy(v)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        return _validate_node_status(v)


class BuildingCreate(BuildingBase):
    pass


class BuildingUpdate(BaseModel):
    area_id: int | None = None
    building_code: str | None = Field(default=None, min_length=1, max_length=64)
    building_name: str | None = Field(default=None, min_length=1, max_length=128)
    total_floors: int | None = Field(default=None, ge=1, le=200)
    gender_policy: str | None = None
    manager_user_id: int | None = None
    status: str | None = None
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("gender_policy")
    @classmethod
    def validate_gender_policy(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_gender_policy(v)
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_node_status(v)
        return v


class BuildingOut(BaseModel):
    id: int
    area_id: int
    building_code: str
    building_name: str
    total_floors: int | None = None
    gender_policy: str
    manager_user_id: int | None = None
    status: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class FloorBase(BaseModel):
    building_id: int
    floor_no: int = Field(ge=-5, le=200)
    floor_name: str | None = Field(default=None, max_length=64)
    gender_policy: str = Field(default="any")
    status: str = Field(default="active")

    @field_validator("gender_policy")
    @classmethod
    def validate_gender_policy(cls, v: str) -> str:
        return _validate_gender_policy(v)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        return _validate_node_status(v)


class FloorCreate(FloorBase):
    pass


class FloorUpdate(BaseModel):
    building_id: int | None = None
    floor_no: int | None = Field(default=None, ge=-5, le=200)
    floor_name: str | None = Field(default=None, max_length=64)
    gender_policy: str | None = None
    status: str | None = None

    @field_validator("gender_policy")
    @classmethod
    def validate_gender_policy(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_gender_policy(v)
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_node_status(v)
        return v


class FloorOut(BaseModel):
    id: int
    building_id: int
    floor_no: int
    floor_name: str | None = None
    gender_policy: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class RoomBase(BaseModel):
    floor_id: int
    room_no: str = Field(min_length=1, max_length=32)
    room_type: str = Field(default="standard", max_length=32)
    capacity: int = Field(default=4, ge=1, le=20)
    gender_policy: str = Field(default="any")
    status: str = Field(default="active")
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("gender_policy")
    @classmethod
    def validate_gender_policy(cls, v: str) -> str:
        return _validate_gender_policy(v)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        return _validate_node_status(v)


class RoomCreate(RoomBase):
    bed_count: int | None = Field(default=None, ge=0, le=20)
    bed_no_prefix: str = Field(default="B", max_length=8)


class RoomUpdate(BaseModel):
    floor_id: int | None = None
    room_no: str | None = Field(default=None, min_length=1, max_length=32)
    room_type: str | None = Field(default=None, max_length=32)
    capacity: int | None = Field(default=None, ge=1, le=20)
    gender_policy: str | None = None
    status: str | None = None
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("gender_policy")
    @classmethod
    def validate_gender_policy(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_gender_policy(v)
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_node_status(v)
        return v


class RoomOut(BaseModel):
    id: int
    floor_id: int
    room_no: str
    room_type: str
    capacity: int
    gender_policy: str
    status: str
    description: str | None = None
    bed_count: int = 0
    active_bed_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class BedBase(BaseModel):
    room_id: int
    bed_no: str = Field(min_length=1, max_length=32)
    operational_status: str = Field(default="active")
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("operational_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in BED_STATUS_VALUES:
            raise ValueError(f"operational_status must be one of {sorted(BED_STATUS_VALUES)}")
        return v


class BedCreate(BedBase):
    pass


class BedUpdate(BaseModel):
    bed_no: str | None = Field(default=None, min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("bed_no")
    @classmethod
    def validate_bed_no(cls, v: str | None) -> str | None:
        # operational_status is changed via /disable /enable endpoints
        return v


class BedStatusUpdate(BaseModel):
    operational_status: str

    @field_validator("operational_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in BED_STATUS_VALUES:
            raise ValueError(f"operational_status must be one of {sorted(BED_STATUS_VALUES)}")
        return v


class BedOut(BaseModel):
    id: int
    room_id: int
    bed_no: str
    operational_status: str
    version: int
    description: str | None = None
    # M3 will populate occupancy/reservation; M2 keeps them empty/false.
    occupied: bool = False
    reserved: bool = False
    available: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DormTreeNode(BaseModel):
    id: int
    node_type: str  # area | building | floor | room
    code: str
    name: str
    status: str
    extra: dict = Field(default_factory=dict)
    children: list[DormTreeNode] = Field(default_factory=list)
