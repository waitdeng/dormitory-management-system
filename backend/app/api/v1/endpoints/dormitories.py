"""Dormitory resource endpoints (M2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import CurrentUser, DbSession, get_request_id, require_permission
from app.core.permissions import PERM_BED_MANAGE, PERM_DORM_CREATE, PERM_DORM_UPDATE, PERM_DORM_VIEW
from app.schemas.common import PageEnvelope
from app.schemas.dorm import (
    BedCreate,
    BedOut,
    BedUpdate,
    BuildingCreate,
    BuildingOut,
    BuildingUpdate,
    DormAreaCreate,
    DormAreaOut,
    DormAreaUpdate,
    DormTreeNode,
    FloorCreate,
    FloorOut,
    FloorUpdate,
    RoomCreate,
    RoomOut,
    RoomUpdate,
)
from app.services import dorm_service

router = APIRouter(tags=["dormitories"])

ViewDorm = Annotated[CurrentUser, Depends(require_permission(PERM_DORM_VIEW))]
CreateDorm = Annotated[CurrentUser, Depends(require_permission(PERM_DORM_CREATE))]
UpdateDorm = Annotated[CurrentUser, Depends(require_permission(PERM_DORM_UPDATE))]
ManageBed = Annotated[CurrentUser, Depends(require_permission(PERM_BED_MANAGE))]


# ---- Areas ----

@router.get("/dorm-areas", response_model=PageEnvelope[DormAreaOut])
async def list_areas(
    db: DbSession,
    _guard: ViewDorm,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    status: str | None = Query(None, max_length=16),
) -> PageEnvelope[DormAreaOut]:
    items, total = await dorm_service.list_areas(
        db, page=page, page_size=page_size, keyword=keyword, status=status
    )
    return PageEnvelope[DormAreaOut](items=items, total=total, page=page, page_size=page_size)


@router.post("/dorm-areas", response_model=DormAreaOut, status_code=201)
async def create_area(
    payload: DormAreaCreate,
    request: Request,
    db: DbSession,
    guard: CreateDorm,
) -> DormAreaOut:
    data = await dorm_service.create_area(
        db, payload, actor_user_id=guard.id, request_id=get_request_id(request)
    )
    return DormAreaOut(**data)


@router.patch("/dorm-areas/{area_id}", response_model=DormAreaOut)
async def update_area(
    area_id: int,
    payload: DormAreaUpdate,
    request: Request,
    db: DbSession,
    guard: UpdateDorm,
) -> DormAreaOut:
    data = await dorm_service.update_area(
        db, area_id, payload, actor_user_id=guard.id, request_id=get_request_id(request)
    )
    return DormAreaOut(**data)


# ---- Buildings ----

@router.get("/buildings", response_model=PageEnvelope[BuildingOut])
async def list_buildings(
    db: DbSession,
    _guard: ViewDorm,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    area_id: int | None = Query(None, ge=1),
    keyword: str | None = Query(None, max_length=64),
    status: str | None = Query(None, max_length=16),
) -> PageEnvelope[BuildingOut]:
    items, total = await dorm_service.list_buildings(
        db,
        page=page,
        page_size=page_size,
        area_id=area_id,
        keyword=keyword,
        status=status,
    )
    return PageEnvelope[BuildingOut](items=items, total=total, page=page, page_size=page_size)


@router.post("/buildings", response_model=BuildingOut, status_code=201)
async def create_building(
    payload: BuildingCreate,
    request: Request,
    db: DbSession,
    guard: CreateDorm,
) -> BuildingOut:
    data = await dorm_service.create_building(
        db, payload, actor_user_id=guard.id, request_id=get_request_id(request)
    )
    return BuildingOut(**data)


@router.patch("/buildings/{building_id}", response_model=BuildingOut)
async def update_building(
    building_id: int,
    payload: BuildingUpdate,
    request: Request,
    db: DbSession,
    guard: UpdateDorm,
) -> BuildingOut:
    data = await dorm_service.update_building(
        db, building_id, payload, actor_user_id=guard.id, request_id=get_request_id(request)
    )
    return BuildingOut(**data)


@router.get("/buildings/{building_id}/occupancy")
async def building_occupancy(
    building_id: int,
    db: DbSession,
    _guard: ViewDorm,
):
    return await dorm_service.building_occupancy(db, building_id)


@router.get("/buildings/{building_id}/floors", response_model=PageEnvelope[FloorOut])
async def list_building_floors(
    building_id: int,
    db: DbSession,
    _guard: ViewDorm,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = Query(None, max_length=16),
) -> PageEnvelope[FloorOut]:
    items, total = await dorm_service.list_floors(
        db, building_id=building_id, page=page, page_size=page_size, status=status
    )
    return PageEnvelope[FloorOut](items=items, total=total, page=page, page_size=page_size)


# ---- Floors ----

@router.post("/floors", response_model=FloorOut, status_code=201)
async def create_floor(
    payload: FloorCreate,
    request: Request,
    db: DbSession,
    guard: CreateDorm,
) -> FloorOut:
    data = await dorm_service.create_floor(
        db, payload, actor_user_id=guard.id, request_id=get_request_id(request)
    )
    return FloorOut(**data)


@router.patch("/floors/{floor_id}", response_model=FloorOut)
async def update_floor(
    floor_id: int,
    payload: FloorUpdate,
    request: Request,
    db: DbSession,
    guard: UpdateDorm,
) -> FloorOut:
    data = await dorm_service.update_floor(
        db, floor_id, payload, actor_user_id=guard.id, request_id=get_request_id(request)
    )
    return FloorOut(**data)


# ---- Rooms ----

@router.get("/rooms", response_model=PageEnvelope[RoomOut])
async def list_rooms(
    db: DbSession,
    _guard: ViewDorm,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    floor_id: int | None = Query(None, ge=1),
    building_id: int | None = Query(None, ge=1),
    keyword: str | None = Query(None, max_length=32),
    status: str | None = Query(None, max_length=16),
) -> PageEnvelope[RoomOut]:
    items, total = await dorm_service.list_rooms(
        db,
        page=page,
        page_size=page_size,
        floor_id=floor_id,
        building_id=building_id,
        keyword=keyword,
        status=status,
    )
    return PageEnvelope[RoomOut](items=items, total=total, page=page, page_size=page_size)


@router.post("/rooms", response_model=RoomOut, status_code=201)
async def create_room(
    payload: RoomCreate,
    request: Request,
    db: DbSession,
    guard: CreateDorm,
) -> RoomOut:
    data = await dorm_service.create_room(
        db, payload, actor_user_id=guard.id, request_id=get_request_id(request)
    )
    return RoomOut(**data)


@router.get("/rooms/{room_id}", response_model=RoomOut)
async def get_room(
    room_id: int,
    db: DbSession,
    _guard: ViewDorm,
) -> RoomOut:
    return RoomOut(**await dorm_service.get_room(db, room_id))


@router.patch("/rooms/{room_id}", response_model=RoomOut)
async def update_room(
    room_id: int,
    payload: RoomUpdate,
    request: Request,
    db: DbSession,
    guard: UpdateDorm,
) -> RoomOut:
    data = await dorm_service.update_room(
        db, room_id, payload, actor_user_id=guard.id, request_id=get_request_id(request)
    )
    return RoomOut(**data)


# ---- Beds ----

@router.get("/rooms/{room_id}/beds", response_model=list[BedOut])
async def list_room_beds(
    room_id: int,
    db: DbSession,
    _guard: ViewDorm,
    status: str | None = Query(None, max_length=16),
) -> list[BedOut]:
    return [BedOut(**b) for b in await dorm_service.list_beds(db, room_id=room_id, status=status)]


@router.post("/rooms/{room_id}/beds", response_model=BedOut, status_code=201)
async def create_room_bed(
    room_id: int,
    payload: BedCreate,
    request: Request,
    db: DbSession,
    guard: ManageBed,
) -> BedOut:
    data = payload.model_copy(update={"room_id": room_id})
    result = await dorm_service.create_bed(
        db, data, actor_user_id=guard.id, request_id=get_request_id(request)
    )
    return BedOut(**result)


@router.patch("/beds/{bed_id}", response_model=BedOut)
async def update_bed(
    bed_id: int,
    payload: BedUpdate,
    request: Request,
    db: DbSession,
    guard: ManageBed,
) -> BedOut:
    data = await dorm_service.update_bed(
        db, bed_id, payload, actor_user_id=guard.id, request_id=get_request_id(request)
    )
    return BedOut(**data)


@router.post("/beds/{bed_id}/disable", response_model=BedOut)
async def disable_bed(
    bed_id: int,
    request: Request,
    db: DbSession,
    guard: ManageBed,
) -> BedOut:
    data = await dorm_service.set_bed_status(
        db,
        bed_id,
        "disabled",
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return BedOut(**data)


@router.post("/beds/{bed_id}/enable", response_model=BedOut)
async def enable_bed(
    bed_id: int,
    request: Request,
    db: DbSession,
    guard: ManageBed,
) -> BedOut:
    data = await dorm_service.set_bed_status(
        db,
        bed_id,
        "active",
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return BedOut(**data)


@router.post("/beds/{bed_id}/maintenance", response_model=BedOut)
async def maintenance_bed(
    bed_id: int,
    request: Request,
    db: DbSession,
    guard: ManageBed,
) -> BedOut:
    data = await dorm_service.set_bed_status(
        db,
        bed_id,
        "maintenance",
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return BedOut(**data)


@router.get("/beds/available", response_model=list[BedOut])
async def list_available_beds(
    db: DbSession,
    _guard: ViewDorm,
    area_id: int | None = Query(None, ge=1),
    building_id: int | None = Query(None, ge=1),
    floor_id: int | None = Query(None, ge=1),
    gender_policy: str | None = Query(None, max_length=16),
    limit: int = Query(200, ge=1, le=500),
) -> list[BedOut]:
    rows = await dorm_service.list_available_beds(
        db,
        area_id=area_id,
        building_id=building_id,
        floor_id=floor_id,
        gender_policy=gender_policy,
        limit=limit,
    )
    return [BedOut(**r) for r in rows]


@router.get("/floors/{floor_id}/room-cards")
async def floor_room_cards(
    floor_id: int,
    db: DbSession,
    _guard: ViewDorm,
    gender_policy: str | None = Query(None, max_length=16),
):
    """Visual allocation: rooms on a floor with full bed status and occupants."""
    return await dorm_service.floor_room_cards(db, floor_id, gender_policy=gender_policy)


@router.get("/dormitories/tree", response_model=list[DormTreeNode])
async def dorm_tree(
    db: DbSession,
    _guard: ViewDorm,
    include_disabled: bool = Query(False),
) -> list[DormTreeNode]:
    return await dorm_service.dorm_tree(db, include_disabled=include_disabled)
