"""Dormitory resource service — hierarchy CRUD and bed status (M2)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_access_code, decrypt_access_code
from app.core.exceptions import BusinessRuleError, ConflictError, ResourceNotFound, ValidationError
from app.models.dorm import DormArea, DormBed, DormBuilding, DormFloor, DormRoom, DormRoomType
from app.schemas.dorm import (
    BedCreate,
    BedUpdate,
    BuildingCreate,
    BuildingUpdate,
    DormAreaCreate,
    DormAreaUpdate,
    FloorCreate,
    FloorUpdate,
    RoomCreate,
    RoomUpdate,
)
from app.services import audit_service
from app.services import occupancy as occ


def _area_out(area: DormArea) -> dict:
    return {
        "id": area.id,
        "area_code": area.area_code,
        "area_name": area.area_name,
        "address": area.address,
        "status": area.status,
        "description": area.description,
        "created_at": area.created_at,
        "updated_at": area.updated_at,
    }


def _building_out(b: DormBuilding) -> dict:
    return {
        "id": b.id,
        "area_id": b.area_id,
        "building_code": b.building_code,
        "building_name": b.building_name,
        "total_floors": b.total_floors,
        "gender_policy": b.gender_policy,
        "manager_user_id": b.manager_user_id,
        "status": b.status,
        "description": b.description,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
    }


def _floor_out(f: DormFloor) -> dict:
    return {
        "id": f.id,
        "building_id": f.building_id,
        "floor_no": f.floor_no,
        "floor_name": f.floor_name,
        "gender_policy": f.gender_policy,
        "status": f.status,
        "created_at": f.created_at,
        "updated_at": f.updated_at,
    }


def _room_out(room: DormRoom, bed_count: int = 0, active_bed_count: int = 0) -> dict:
    return {
        "id": room.id,
        "floor_id": room.floor_id,
        "room_no": room.room_no,
        "room_type": room.room_type,
        "capacity": room.capacity,
        "gender_policy": room.gender_policy,
        "status": room.status,
        "description": room.description,
        "bed_count": bed_count,
        "active_bed_count": active_bed_count,
        # FEAT-008: plaintext never leaves the reveal endpoint
        "has_access_code": room.access_code_encrypted is not None,
        "created_at": room.created_at,
        "updated_at": room.updated_at,
    }


def _bed_out(
    bed: DormBed,
    *,
    occupied: bool = False,
    reserved: bool = False,
    location: dict | None = None,
) -> dict:
    """Bed view. Occupied/reserved come from M3 relation tables, never stored here."""
    available = bed.operational_status == "active" and not occupied and not reserved
    loc = location or {}
    area_name = loc.get("area_name")
    building_name = loc.get("building_name")
    floor_no = loc.get("floor_no")
    room_no = loc.get("room_no")
    bed_path = None
    if building_name is not None:
        bed_path = "/".join(
            str(p)
            for p in (area_name, building_name, floor_no, room_no, bed.bed_no)
            if p is not None and p != ""
        )
    return {
        "id": bed.id,
        "room_id": bed.room_id,
        "bed_no": bed.bed_no,
        "operational_status": bed.operational_status,
        "version": bed.version,
        "description": bed.description,
        "occupied": occupied,
        "reserved": reserved,
        "available": available,
        "area_name": area_name,
        "building_name": building_name,
        "floor_no": floor_no,
        "room_no": room_no,
        "bed_path": bed_path,
        "created_at": bed.created_at,
        "updated_at": bed.updated_at,
    }


async def _load_area(db: AsyncSession, area_id: int) -> DormArea:
    row = (
        await db.execute(
            select(DormArea).where(DormArea.id == area_id).execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFound(f"Dorm area {area_id} not found")
    return row


async def _load_building(db: AsyncSession, building_id: int) -> DormBuilding:
    row = (
        await db.execute(
            select(DormBuilding)
            .where(DormBuilding.id == building_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFound(f"Building {building_id} not found")
    return row


async def _load_floor(db: AsyncSession, floor_id: int) -> DormFloor:
    row = (
        await db.execute(
            select(DormFloor)
            .where(DormFloor.id == floor_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFound(f"Floor {floor_id} not found")
    return row


async def _load_room(db: AsyncSession, room_id: int) -> DormRoom:
    row = (
        await db.execute(
            select(DormRoom).where(DormRoom.id == room_id).execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFound(f"Room {room_id} not found")
    return row


async def _load_bed(db: AsyncSession, bed_id: int) -> DormBed:
    row = (
        await db.execute(
            select(DormBed).where(DormBed.id == bed_id).execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFound(f"Bed {bed_id} not found")
    return row


async def _assert_allocatable(
    db: AsyncSession, *, floor_id: int
) -> tuple[DormFloor, DormBuilding, DormArea]:
    floor = await _load_floor(db, floor_id)
    building = await _load_building(db, floor.building_id)
    area = await _load_area(db, building.area_id)
    for label, node in (("area", area), ("building", building), ("floor", floor)):
        if node.status != "active":
            raise ValidationError(f"{label} is disabled and cannot accept new resources")
    return floor, building, area


# ---- Areas ----

async def list_areas(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    query = select(DormArea)
    count_query = select(func.count()).select_from(DormArea)
    if keyword:
        pattern = f"%{keyword}%"
        cond = (DormArea.area_code.ilike(pattern)) | (DormArea.area_name.ilike(pattern))
        query = query.where(cond)
        count_query = count_query.where(cond)
    if status:
        query = query.where(DormArea.status == status)
        count_query = count_query.where(DormArea.status == status)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(DormArea.area_code).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return [_area_out(r) for r in rows], total


async def create_area(
    db: AsyncSession,
    payload: DormAreaCreate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    existing = (
        await db.execute(select(DormArea).where(DormArea.area_code == payload.area_code))
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Area code '{payload.area_code}' already exists")
    area = DormArea(**payload.model_dump())
    db.add(area)
    await db.flush()
    await audit_service.write_audit(
        db,
        action="dorm_area.create",
        resource_type="dorm_area",
        resource_id=area.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_area_out(area),
    )
    await db.commit()
    return _area_out(await _load_area(db, area.id))


async def update_area(
    db: AsyncSession,
    area_id: int,
    payload: DormAreaUpdate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    area = await _load_area(db, area_id)
    before = _area_out(area)
    data = payload.model_dump(exclude_unset=True)
    if "area_code" in data and data["area_code"] != area.area_code:
        existing = (
            await db.execute(
                select(DormArea).where(
                    DormArea.area_code == data["area_code"], DormArea.id != area_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Area code '{data['area_code']}' already exists")
    for key, value in data.items():
        setattr(area, key, value)
    await audit_service.write_audit(
        db,
        action="dorm_area.update",
        resource_type="dorm_area",
        resource_id=area.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=before,
        after_data=_area_out(area),
    )
    await db.commit()
    return _area_out(await _load_area(db, area.id))


# ---- Buildings ----

async def list_buildings(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    area_id: int | None = None,
    keyword: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    query = select(DormBuilding)
    count_query = select(func.count()).select_from(DormBuilding)
    if area_id is not None:
        query = query.where(DormBuilding.area_id == area_id)
        count_query = count_query.where(DormBuilding.area_id == area_id)
    if keyword:
        pattern = f"%{keyword}%"
        cond = (DormBuilding.building_code.ilike(pattern)) | (
            DormBuilding.building_name.ilike(pattern)
        )
        query = query.where(cond)
        count_query = count_query.where(cond)
    if status:
        query = query.where(DormBuilding.status == status)
        count_query = count_query.where(DormBuilding.status == status)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(DormBuilding.building_code)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return [_building_out(r) for r in rows], total


async def create_building(
    db: AsyncSession,
    payload: BuildingCreate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    area = await _load_area(db, payload.area_id)
    if area.status != "active":
        raise ValidationError(f"Area '{area.area_code}' is disabled")
    existing = (
        await db.execute(
            select(DormBuilding).where(
                DormBuilding.area_id == payload.area_id,
                DormBuilding.building_code == payload.building_code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"Building code '{payload.building_code}' already exists in this area"
        )
    building = DormBuilding(**payload.model_dump())
    db.add(building)
    await db.flush()
    await audit_service.write_audit(
        db,
        action="dorm_building.create",
        resource_type="dorm_building",
        resource_id=building.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_building_out(building),
    )
    await db.commit()
    return _building_out(await _load_building(db, building.id))


async def update_building(
    db: AsyncSession,
    building_id: int,
    payload: BuildingUpdate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    building = await _load_building(db, building_id)
    before = _building_out(building)
    data = payload.model_dump(exclude_unset=True)
    if "area_id" in data and data["area_id"] != building.area_id:
        area = await _load_area(db, data["area_id"])
        if area.status != "active":
            raise ValidationError(f"Area '{area.area_code}' is disabled")
    if (
        "building_code" in data
        and data["building_code"] != building.building_code
        or "area_id" in data
        and data["area_id"] != building.area_id
    ):
        area_id = data.get("area_id", building.area_id)
        code = data.get("building_code", building.building_code)
        existing = (
            await db.execute(
                select(DormBuilding).where(
                    DormBuilding.area_id == area_id,
                    DormBuilding.building_code == code,
                    DormBuilding.id != building_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Building code '{code}' already exists in this area")
    for key, value in data.items():
        setattr(building, key, value)
    await audit_service.write_audit(
        db,
        action="dorm_building.update",
        resource_type="dorm_building",
        resource_id=building.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=before,
        after_data=_building_out(building),
    )
    await db.commit()
    return _building_out(await _load_building(db, building.id))


# ---- Floors ----

async def list_floors(
    db: AsyncSession,
    *,
    building_id: int,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
) -> tuple[list[dict], int]:
    query = select(DormFloor).where(DormFloor.building_id == building_id)
    count_query = (
        select(func.count())
        .select_from(DormFloor)
        .where(DormFloor.building_id == building_id)
    )
    if status:
        query = query.where(DormFloor.status == status)
        count_query = count_query.where(DormFloor.status == status)
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(DormFloor.floor_no).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return [_floor_out(r) for r in rows], total


async def create_floor(
    db: AsyncSession,
    payload: FloorCreate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    building = await _load_building(db, payload.building_id)
    if building.status != "active":
        raise ValidationError(f"Building '{building.building_code}' is disabled")
    area = await _load_area(db, building.area_id)
    if area.status != "active":
        raise ValidationError(f"Area '{area.area_code}' is disabled")
    existing = (
        await db.execute(
            select(DormFloor).where(
                DormFloor.building_id == payload.building_id,
                DormFloor.floor_no == payload.floor_no,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"Floor {payload.floor_no} already exists in building '{building.building_code}'"
        )
    floor = DormFloor(**payload.model_dump())
    db.add(floor)
    await db.flush()
    await audit_service.write_audit(
        db,
        action="dorm_floor.create",
        resource_type="dorm_floor",
        resource_id=floor.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_floor_out(floor),
    )
    await db.commit()
    return _floor_out(await _load_floor(db, floor.id))


async def update_floor(
    db: AsyncSession,
    floor_id: int,
    payload: FloorUpdate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    floor = await _load_floor(db, floor_id)
    before = _floor_out(floor)
    data = payload.model_dump(exclude_unset=True)
    if (
        "floor_no" in data
        and data["floor_no"] != floor.floor_no
        or "building_id" in data
        and data["building_id"] != floor.building_id
    ):
        building_id = data.get("building_id", floor.building_id)
        floor_no = data.get("floor_no", floor.floor_no)
        existing = (
            await db.execute(
                select(DormFloor).where(
                    DormFloor.building_id == building_id,
                    DormFloor.floor_no == floor_no,
                    DormFloor.id != floor_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Floor {floor_no} already exists in this building")
    for key, value in data.items():
        setattr(floor, key, value)
    await audit_service.write_audit(
        db,
        action="dorm_floor.update",
        resource_type="dorm_floor",
        resource_id=floor.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=before,
        after_data=_floor_out(floor),
    )
    await db.commit()
    return _floor_out(await _load_floor(db, floor.id))


# ---- Rooms ----

async def _room_bed_counts(db: AsyncSession, room_id: int) -> tuple[int, int]:
    total = (
        await db.execute(
            select(func.count()).select_from(DormBed).where(DormBed.room_id == room_id)
        )
    ).scalar_one()
    active = (
        await db.execute(
            select(func.count())
            .select_from(DormBed)
            .where(DormBed.room_id == room_id, DormBed.operational_status == "active")
        )
    ).scalar_one()
    return total, active


async def list_rooms(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    floor_id: int | None = None,
    building_id: int | None = None,
    keyword: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    query = select(DormRoom)
    count_query = select(func.count()).select_from(DormRoom)

    if floor_id is not None:
        query = query.where(DormRoom.floor_id == floor_id)
        count_query = count_query.where(DormRoom.floor_id == floor_id)
    if building_id is not None:
        query = query.where(
            DormRoom.floor_id.in_(select(DormFloor.id).where(DormFloor.building_id == building_id))
        )
        count_query = count_query.where(
            DormRoom.floor_id.in_(select(DormFloor.id).where(DormFloor.building_id == building_id))
        )
    if keyword:
        pattern = f"%{keyword}%"
        query = query.where(DormRoom.room_no.ilike(pattern))
        count_query = count_query.where(DormRoom.room_no.ilike(pattern))
    if status:
        query = query.where(DormRoom.status == status)
        count_query = count_query.where(DormRoom.status == status)

    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(DormRoom.floor_id, DormRoom.room_no)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    items = []
    for room in rows:
        bed_count, active_count = await _room_bed_counts(db, room.id)
        items.append(_room_out(room, bed_count, active_count))
    return items, total


async def get_room(db: AsyncSession, room_id: int) -> dict:
    room = await _load_room(db, room_id)
    bed_count, active_count = await _room_bed_counts(db, room_id)
    return _room_out(room, bed_count, active_count)


async def create_room(
    db: AsyncSession,
    payload: RoomCreate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    await _assert_allocatable(db, floor_id=payload.floor_id)
    existing = (
        await db.execute(
            select(DormRoom).where(
                DormRoom.floor_id == payload.floor_id, DormRoom.room_no == payload.room_no
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Room '{payload.room_no}' already exists on this floor")

    data = payload.model_dump(exclude={"bed_count", "bed_no_prefix", "access_code"})
    access_code = payload.access_code
    if access_code is not None and access_code != "":
        data["access_code_encrypted"] = encrypt_access_code(access_code)
    room = DormRoom(**data)
    db.add(room)
    await db.flush()

    bed_count = payload.bed_count if payload.bed_count is not None else payload.capacity
    if bed_count > payload.capacity:
        raise ValidationError("bed_count cannot exceed room capacity")
    prefix = payload.bed_no_prefix or "B"
    for i in range(1, bed_count + 1):
        db.add(DormBed(room_id=room.id, bed_no=f"{prefix}{i}", operational_status="active"))
    await db.flush()

    await audit_service.write_audit(
        db,
        action="dorm_room.create",
        resource_type="dorm_room",
        resource_id=room.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_room_out(room, bed_count, bed_count),
    )
    await db.commit()
    return await get_room(db, room.id)


async def update_room(
    db: AsyncSession,
    room_id: int,
    payload: RoomUpdate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    room = await _load_room(db, room_id)
    before = _room_out(room)
    data = payload.model_dump(exclude_unset=True)

    if "floor_id" in data and data["floor_id"] != room.floor_id:
        await _assert_allocatable(db, floor_id=data["floor_id"])
    if (
        "room_no" in data
        and data["room_no"] != room.room_no
        or "floor_id" in data
        and data["floor_id"] != room.floor_id
    ):
        floor_id = data.get("floor_id", room.floor_id)
        room_no = data.get("room_no", room.room_no)
        existing = (
            await db.execute(
                select(DormRoom).where(
                    DormRoom.floor_id == floor_id,
                    DormRoom.room_no == room_no,
                    DormRoom.id != room_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Room '{room_no}' already exists on this floor")

    if "capacity" in data and data["capacity"] is not None:
        bed_total = (
            await db.execute(
                select(func.count()).select_from(DormBed).where(DormBed.room_id == room_id)
            )
        ).scalar_one()
        if data["capacity"] < bed_total:
            raise BusinessRuleError(
                f"capacity {data['capacity']} is less than existing bed count {bed_total}"
            )

    # FEAT-008: access_code is encrypted at rest; never store plaintext
    access_code = data.pop("access_code", None)
    if "access_code" in payload.model_fields_set:
        if access_code is None or access_code == "":
            room.access_code_encrypted = None
        else:
            room.access_code_encrypted = encrypt_access_code(access_code)

    for key, value in data.items():
        setattr(room, key, value)

    await audit_service.write_audit(
        db,
        action="dorm_room.update",
        resource_type="dorm_room",
        resource_id=room.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=before,
        after_data=_room_out(room),
    )
    await db.commit()
    return await get_room(db, room.id)


# ---- Beds ----

async def list_beds(
    db: AsyncSession,
    *,
    room_id: int,
    status: str | None = None,
) -> list[dict]:
    query = select(DormBed).where(DormBed.room_id == room_id)
    if status:
        query = query.where(DormBed.operational_status == status)
    rows = (await db.execute(query.order_by(DormBed.bed_no))).scalars().all()
    flags = await occ.derive_bed_flags(db, [r.id for r in rows])
    out = []
    for r in rows:
        f = flags.get(r.id, {"occupied": False, "reserved": False})
        out.append(_bed_out(r, occupied=f["occupied"], reserved=f["reserved"]))
    return out


async def create_bed(
    db: AsyncSession,
    payload: BedCreate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    room = await _load_room(db, payload.room_id)
    await _assert_allocatable(db, floor_id=room.floor_id)

    existing = (
        await db.execute(
            select(DormBed).where(
                DormBed.room_id == payload.room_id, DormBed.bed_no == payload.bed_no
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Bed '{payload.bed_no}' already exists in this room")

    bed_total = (
        await db.execute(
            select(func.count()).select_from(DormBed).where(DormBed.room_id == payload.room_id)
        )
    ).scalar_one()
    if bed_total >= room.capacity:
        raise BusinessRuleError(
            f"Room '{room.room_no}' already has {bed_total} beds (capacity {room.capacity})"
        )

    bed = DormBed(**payload.model_dump())
    db.add(bed)
    await db.flush()
    await audit_service.write_audit(
        db,
        action="dorm_bed.create",
        resource_type="dorm_bed",
        resource_id=bed.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_bed_out(bed),
    )
    await db.commit()
    return _bed_out(await _load_bed(db, bed.id))


async def update_bed(
    db: AsyncSession,
    bed_id: int,
    payload: BedUpdate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    bed = await _load_bed(db, bed_id)
    before = _bed_out(bed)
    data = payload.model_dump(exclude_unset=True)
    if "bed_no" in data and data["bed_no"] != bed.bed_no:
        existing = (
            await db.execute(
                select(DormBed).where(
                    DormBed.room_id == bed.room_id,
                    DormBed.bed_no == data["bed_no"],
                    DormBed.id != bed_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Bed '{data['bed_no']}' already exists in this room")
        bed.bed_no = data["bed_no"]
    if "description" in data:
        bed.description = data["description"]
    await audit_service.write_audit(
        db,
        action="dorm_bed.update",
        resource_type="dorm_bed",
        resource_id=bed.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=before,
        after_data=_bed_out(bed),
    )
    await db.commit()
    return _bed_out(await _load_bed(db, bed.id))


async def set_bed_status(
    db: AsyncSession,
    bed_id: int,
    operational_status: str,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    if operational_status not in {"active", "maintenance", "disabled"}:
        raise ValidationError(
            "operational_status must be active, maintenance or disabled"
        )
    bed = await _load_bed(db, bed_id)
    flags = await occ.derive_bed_flags(db, [bed_id])
    f = flags.get(bed_id, {"occupied": False, "reserved": False})
    before = _bed_out(bed, occupied=f["occupied"], reserved=f["reserved"])

    # BR-009 / spec §6.3: disable refuses occupied or reserved beds.
    # Maintenance is allowed with residents but they remain visible as occupied.
    if operational_status == "disabled" and (f["occupied"] or f["reserved"]):
        raise ConflictError(
            "Cannot disable a bed that is currently occupied or reserved"
        )

    if bed.operational_status != operational_status:
        bed.operational_status = operational_status
        bed.version += 1

    await audit_service.write_audit(
        db,
        action="dorm_bed.set_status",
        resource_type="dorm_bed",
        resource_id=bed.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=before,
        after_data=_bed_out(bed, occupied=f["occupied"], reserved=f["reserved"]),
    )
    await db.commit()
    reloaded = await _load_bed(db, bed_id)
    flags2 = await occ.derive_bed_flags(db, [bed_id])
    f2 = flags2.get(bed_id, {"occupied": False, "reserved": False})
    return _bed_out(reloaded, occupied=f2["occupied"], reserved=f2["reserved"])


async def list_available_beds(
    db: AsyncSession,
    *,
    area_id: int | None = None,
    building_id: int | None = None,
    floor_id: int | None = None,
    gender_policy: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Available beds with full location path (BUG-005)."""
    stmt = (
        select(
            DormBed,
            DormArea.area_name,
            DormBuilding.building_name,
            DormFloor.floor_no,
            DormRoom.room_no,
        )
        .join(DormRoom, DormBed.room_id == DormRoom.id)
        .join(DormFloor, DormRoom.floor_id == DormFloor.id)
        .join(DormBuilding, DormFloor.building_id == DormBuilding.id)
        .join(DormArea, DormBuilding.area_id == DormArea.id)
        .where(
            DormBed.operational_status == "active",
            DormRoom.status == "active",
            DormFloor.status == "active",
            DormBuilding.status == "active",
            DormArea.status == "active",
        )
    )
    if area_id is not None:
        stmt = stmt.where(DormArea.id == area_id)
    if building_id is not None:
        stmt = stmt.where(DormBuilding.id == building_id)
    if floor_id is not None:
        stmt = stmt.where(DormFloor.id == floor_id)
    if gender_policy and gender_policy != "any":
        stmt = stmt.where(
            (DormRoom.gender_policy == gender_policy)
            | (DormRoom.gender_policy == "any")
        )
    rows_all = (await db.execute(stmt.order_by(DormBed.id).limit(limit))).all()
    beds = [row[0] for row in rows_all]
    flags = await occ.derive_bed_flags(db, [b.id for b in beds])
    out = []
    for row in rows_all:
        r, area_name, building_name, floor_no, room_no = row
        f = flags.get(r.id, {"occupied": False, "reserved": False})
        item = _bed_out(
            r,
            occupied=f["occupied"],
            reserved=f["reserved"],
            location={
                "area_name": area_name,
                "building_name": building_name,
                "floor_no": floor_no,
                "room_no": room_no,
            },
        )
        if item["available"]:
            out.append(item)
    return out


async def dorm_tree(db: AsyncSession, *, include_disabled: bool = False) -> list[dict]:
    areas = (
        await db.execute(select(DormArea).order_by(DormArea.area_code))
    ).scalars().all()
    buildings = (
        await db.execute(select(DormBuilding).order_by(DormBuilding.building_code))
    ).scalars().all()
    floors = (
        await db.execute(select(DormFloor).order_by(DormFloor.floor_no))
    ).scalars().all()
    rooms = (
        await db.execute(select(DormRoom).order_by(DormRoom.room_no))
    ).scalars().all()

    beds_by_room: dict[int, list[DormBed]] = {}
    for bed in (await db.execute(select(DormBed).order_by(DormBed.bed_no))).scalars():
        beds_by_room.setdefault(bed.room_id, []).append(bed)

    buildings_by_area: dict[int, list[DormBuilding]] = {}
    for b in buildings:
        buildings_by_area.setdefault(b.area_id, []).append(b)
    floors_by_building: dict[int, list[DormFloor]] = {}
    for f in floors:
        floors_by_building.setdefault(f.building_id, []).append(f)
    rooms_by_floor: dict[int, list[DormRoom]] = {}
    for r in rooms:
        rooms_by_floor.setdefault(r.floor_id, []).append(r)

    def room_node(room: DormRoom) -> dict:
        bed_list = beds_by_room.get(room.id, [])
        return {
            "id": room.id,
            "node_type": "room",
            "code": room.room_no,
            "name": room.room_no,
            "status": room.status,
            "extra": {
                "capacity": room.capacity,
                "bed_count": len(bed_list),
                "active_bed_count": sum(
                    1 for b in bed_list if b.operational_status == "active"
                ),
                "gender_policy": room.gender_policy,
                "floor_id": room.floor_id,
            },
            "children": [],
        }

    def floor_node(floor: DormFloor) -> dict:
        children = [room_node(r) for r in rooms_by_floor.get(floor.id, [])]
        if not include_disabled:
            children = [c for c in children if c["status"] == "active"]
        return {
            "id": floor.id,
            "node_type": "floor",
            "code": str(floor.floor_no),
            "name": floor.floor_name or f"{floor.floor_no}F",
            "status": floor.status,
            "extra": {"gender_policy": floor.gender_policy},
            "children": children,
        }

    def building_node(building: DormBuilding) -> dict:
        children = [floor_node(f) for f in floors_by_building.get(building.id, [])]
        if not include_disabled:
            children = [c for c in children if c["status"] == "active"]
        return {
            "id": building.id,
            "node_type": "building",
            "code": building.building_code,
            "name": building.building_name,
            "status": building.status,
            "extra": {
                "gender_policy": building.gender_policy,
                "total_floors": building.total_floors,
            },
            "children": children,
        }

    tree: list[dict] = []
    for area in areas:
        if not include_disabled and area.status != "active":
            continue
        children = [building_node(b) for b in buildings_by_area.get(area.id, [])]
        if not include_disabled:
            children = [c for c in children if c["status"] == "active"]
        tree.append(
            {
                "id": area.id,
                "node_type": "area",
                "code": area.area_code,
                "name": area.area_name,
                "status": area.status,
                "extra": {"address": area.address},
                "children": children,
            }
        )
    return tree


async def building_occupancy(db: AsyncSession, building_id: int) -> dict:
    building = await _load_building(db, building_id)
    floor_ids = select(DormFloor.id).where(DormFloor.building_id == building_id)
    room_ids = select(DormRoom.id).where(DormRoom.floor_id.in_(floor_ids))

    room_count = (
        await db.execute(
            select(func.count()).select_from(DormRoom).where(DormRoom.id.in_(room_ids))
        )
    ).scalar_one()
    bed_count = (
        await db.execute(
            select(func.count()).select_from(DormBed).where(DormBed.room_id.in_(room_ids))
        )
    ).scalar_one()
    active_beds = (
        await db.execute(
            select(func.count())
            .select_from(DormBed)
            .where(
                DormBed.room_id.in_(room_ids),
                DormBed.operational_status == "active",
            )
        )
    ).scalar_one()
    all_bed_ids = (
        await db.execute(select(DormBed.id).where(DormBed.room_id.in_(room_ids)))
    ).scalars().all()
    usage = await occ.count_bed_usage(db, list(all_bed_ids))
    free_active = min(active_beds, usage["free"])
    rate = None
    if active_beds > 0:
        rate = round(usage["occupied"] / active_beds, 4)

    return {
        "building_id": building.id,
        "building_code": building.building_code,
        "building_name": building.building_name,
        "room_count": room_count,
        "bed_count": bed_count,
        "available_bed_count": free_active,
        "occupied_bed_count": usage["occupied"],
        "reserved_bed_count": usage["reserved"],
        "occupancy_rate": rate,
    }


async def floor_room_cards(
    db: AsyncSession, floor_id: int, *, gender_policy: str | None = None
) -> list[dict]:
    """Room cards with full bed status for visual bed allocation (M5)."""
    from app.models.accommodation import AccommodationRecord, BedReservation
    from app.models.employee import Employee

    await _load_floor(db, floor_id)
    rooms = (
        await db.execute(
            select(DormRoom)
            .where(DormRoom.floor_id == floor_id, DormRoom.status == "active")
            .order_by(DormRoom.room_no)
        )
    ).scalars().all()
    room_ids = [r.id for r in rooms]
    if not room_ids:
        return []

    beds = (
        await db.execute(
            select(DormBed).where(DormBed.room_id.in_(room_ids)).order_by(DormBed.bed_no)
        )
    ).scalars().all()
    flags = await occ.derive_bed_flags(db, [b.id for b in beds])

    # occupant / reservation employee info
    occ_rows = (
        await db.execute(
            select(AccommodationRecord.bed_id, AccommodationRecord.employee_id).where(
                AccommodationRecord.bed_id.in_([b.id for b in beds]),
                AccommodationRecord.status == "active",
            )
        )
    ).all()
    res_rows = (
        await db.execute(
            select(BedReservation.bed_id, BedReservation.employee_id).where(
                BedReservation.bed_id.in_([b.id for b in beds]),
                BedReservation.status == "active",
            )
        )
    ).all()
    emp_ids = {e for _, e in occ_rows} | {e for _, e in res_rows}
    emp_map: dict[int, dict] = {}
    if emp_ids:
        for e in (
            await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))
        ).scalars():
            emp_map[e.id] = {"id": e.id, "employee_no": e.employee_no, "full_name": e.full_name}
    occ_emp = {bed: emp_map.get(e) for bed, e in occ_rows}
    res_emp = {bed: emp_map.get(e) for bed, e in res_rows}

    beds_by_room: dict[int, list[dict]] = {}
    for b in beds:
        f = flags.get(b.id, {"occupied": False, "reserved": False})
        occupied = f["occupied"]
        reserved = f["reserved"]
        beds_by_room.setdefault(b.room_id, []).append(
            {
                **_bed_out(b, occupied=occupied, reserved=reserved),
                "occupant": occ_emp.get(b.id) if occupied else None,
                "reserved_for": res_emp.get(b.id) if reserved else None,
            }
        )

    cards = []
    for room in rooms:
        room_beds = beds_by_room.get(room.id, [])
        if gender_policy and room.gender_policy not in (gender_policy, "any"):
            continue
        occupied_n = sum(1 for b in room_beds if b["occupied"])
        reserved_n = sum(1 for b in room_beds if b["reserved"])
        free_n = sum(1 for b in room_beds if b["available"])
        cards.append(
            {
                **_room_out(room, bed_count=len(room_beds), active_bed_count=sum(
                    1 for b in room_beds if b["operational_status"] == "active"
                )),
                "occupied_count": occupied_n,
                "reserved_count": reserved_n,
                "available_count": free_n,
                "beds": room_beds,
            }
        )
    return cards


async def reveal_room_access_code(
    db: AsyncSession,
    room_id: int,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """FEAT-008: authorized reveal of a room door access code.

    Always audited. Plaintext is returned only here and only with permission.
    """
    room = await _load_room(db, room_id)
    plain = None
    if room.access_code_encrypted:
        plain = decrypt_access_code(room.access_code_encrypted)
    await audit_service.write_audit(
        db,
        action="dorm_room.access_code.reveal",
        resource_type="dorm_room",
        resource_id=room.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={"room_id": room.id, "room_no": room.room_no, "revealed": plain is not None},
    )
    await db.commit()
    return {"room_id": room.id, "access_code": plain}


async def set_room_access_code(
    db: AsyncSession,
    room_id: int,
    access_code: str | None,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """FEAT-008: set/replace/clear door access code (string, preserves leading zeros)."""
    room = await _load_room(db, room_id)
    before_flag = room.access_code_encrypted is not None
    if access_code is None or access_code == "":
        room.access_code_encrypted = None
        action = "dorm_room.access_code.clear"
    else:
        if not isinstance(access_code, str):
            raise ValidationError("access_code must be a string")
        room.access_code_encrypted = encrypt_access_code(access_code)
        action = "dorm_room.access_code.set"
    await audit_service.write_audit(
        db,
        action=action,
        resource_type="dorm_room",
        resource_id=room.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data={"has_access_code": before_flag},
        after_data={"has_access_code": room.access_code_encrypted is not None},
    )
    await db.commit()
    return _room_out(room)


# ---- FEAT-002 room types ----

def _room_type_out(row: DormRoomType) -> dict:
    return {
        "id": row.id,
        "type_code": row.type_code,
        "type_name": row.type_name,
        "default_capacity": row.default_capacity,
        "description": row.description,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def list_room_types(
    db: AsyncSession,
    *,
    include_disabled: bool = True,
) -> list[dict]:
    stmt = select(DormRoomType).order_by(DormRoomType.type_code)
    if not include_disabled:
        stmt = stmt.where(DormRoomType.status == "active")
    rows = (await db.execute(stmt)).scalars().all()
    return [_room_type_out(r) for r in rows]


async def create_room_type(
    db: AsyncSession,
    payload,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    existing = (
        await db.execute(
            select(DormRoomType).where(DormRoomType.type_code == payload.type_code)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Room type '{payload.type_code}' already exists")
    row = DormRoomType(
        type_code=payload.type_code,
        type_name=payload.type_name,
        default_capacity=payload.default_capacity,
        description=payload.description,
        status=payload.status,
    )
    db.add(row)
    await db.flush()
    await audit_service.write_audit(
        db,
        action="dorm_room_type.create",
        resource_type="dorm_room_type",
        resource_id=row.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_room_type_out(row),
    )
    await db.commit()
    return _room_type_out(row)


async def update_room_type(
    db: AsyncSession,
    type_id: int,
    payload,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    row = (
        await db.execute(
            select(DormRoomType).where(DormRoomType.id == type_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFound(f"Room type {type_id} not found")
    before = _room_type_out(row)
    data = payload.model_dump(exclude_unset=True)
    # FEAT-002: renaming a type must NOT change existing room capacity
    for key, value in data.items():
        setattr(row, key, value)
    await audit_service.write_audit(
        db,
        action="dorm_room_type.update",
        resource_type="dorm_room_type",
        resource_id=row.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=before,
        after_data=_room_type_out(row),
    )
    await db.commit()
    return _room_type_out(row)


async def disable_room_type(
    db: AsyncSession,
    type_id: int,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """Archive/disable a room type. Existing rooms keep their capacity unchanged."""
    row = (
        await db.execute(
            select(DormRoomType).where(DormRoomType.id == type_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFound(f"Room type {type_id} not found")
    row.status = "disabled"
    await audit_service.write_audit(
        db,
        action="dorm_room_type.disable",
        resource_type="dorm_room_type",
        resource_id=row.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data=_room_type_out(row),
    )
    await db.commit()
    return _room_type_out(row)


# ---- BUG-001: safe delete with referential checks ----

async def _has_child_or_business_refs(
    db: AsyncSession,
    *,
    area_id: int | None = None,
    building_id: int | None = None,
    floor_id: int | None = None,
    room_id: int | None = None,
    bed_id: int | None = None,
) -> list[str]:
    """Return human-readable blockers. Empty list means safe to hard-delete."""
    from app.models.accommodation import (
        AccommodationRecord,
        BedReservation,
        TransferRecord,
    )

    blockers: list[str] = []

    async def _count(stmt) -> int:
        return (await db.execute(stmt)).scalar_one()

    if bed_id is not None:
        n = await _count(
            select(func.count()).select_from(AccommodationRecord).where(
                AccommodationRecord.bed_id == bed_id
            )
        )
        if n:
            blockers.append(f"床位存在 {n} 条住宿历史/占用记录")
        n = await _count(
            select(func.count()).select_from(BedReservation).where(
                BedReservation.bed_id == bed_id
            )
        )
        if n:
            blockers.append(f"床位存在 {n} 条预留记录")
        n = await _count(
            select(func.count()).select_from(TransferRecord).where(
                (TransferRecord.source_bed_id == bed_id)
                | (TransferRecord.target_bed_id == bed_id)
            )
        )
        if n:
            blockers.append(f"床位存在 {n} 条调宿关联")

    if room_id is not None:
        n = await _count(
            select(func.count()).select_from(DormBed).where(DormBed.room_id == room_id)
        )
        if n:
            blockers.append(f"房间下仍有 {n} 个床位，请先删除床位")
        n = await _count(
            select(func.count())
            .select_from(AccommodationRecord)
            .join(DormBed, AccommodationRecord.bed_id == DormBed.id)
            .where(DormBed.room_id == room_id)
        )
        if n:
            blockers.append(f"房间存在 {n} 条住宿关联")

    if floor_id is not None:
        n = await _count(
            select(func.count()).select_from(DormRoom).where(DormRoom.floor_id == floor_id)
        )
        if n:
            blockers.append(f"楼层下仍有 {n} 个房间")
        n = await _count(
            select(func.count())
            .select_from(AccommodationRecord)
            .join(DormBed, AccommodationRecord.bed_id == DormBed.id)
            .join(DormRoom, DormBed.room_id == DormRoom.id)
            .where(DormRoom.floor_id == floor_id)
        )
        if n:
            blockers.append(f"楼层存在 {n} 条住宿关联")

    if building_id is not None:
        n = await _count(
            select(func.count()).select_from(DormFloor).where(DormFloor.building_id == building_id)
        )
        if n:
            blockers.append(f"楼栋下仍有 {n} 个楼层")
        n = await _count(
            select(func.count())
            .select_from(AccommodationRecord)
            .join(DormBed, AccommodationRecord.bed_id == DormBed.id)
            .join(DormRoom, DormBed.room_id == DormRoom.id)
            .join(DormFloor, DormRoom.floor_id == DormFloor.id)
            .where(DormFloor.building_id == building_id)
        )
        if n:
            blockers.append(f"楼栋存在 {n} 条住宿关联")

    if area_id is not None:
        n = await _count(
            select(func.count()).select_from(DormBuilding).where(DormBuilding.area_id == area_id)
        )
        if n:
            blockers.append(f"区域下仍有 {n} 个楼栋")
        n = await _count(
            select(func.count())
            .select_from(AccommodationRecord)
            .join(DormBed, AccommodationRecord.bed_id == DormBed.id)
            .join(DormRoom, DormBed.room_id == DormRoom.id)
            .join(DormFloor, DormRoom.floor_id == DormFloor.id)
            .join(DormBuilding, DormFloor.building_id == DormBuilding.id)
            .where(DormBuilding.area_id == area_id)
        )
        if n:
            blockers.append(f"区域存在 {n} 条住宿关联")

    return blockers


async def delete_bed(
    db: AsyncSession,
    bed_id: int,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    bed = await _load_bed(db, bed_id)
    blockers = await _has_child_or_business_refs(db, bed_id=bed_id)
    if blockers:
        raise BusinessRuleError(
            "床位存在业务关联，不允许删除，可改为停用：" + "；".join(blockers)
        )
    snapshot = _bed_out(bed)
    await db.delete(bed)
    await audit_service.write_audit(
        db,
        action="dorm_bed.delete",
        resource_type="dorm_bed",
        resource_id=bed_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=snapshot,
    )
    await db.commit()
    return {"deleted": True, "id": bed_id}


async def delete_room(
    db: AsyncSession,
    room_id: int,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    room = await _load_room(db, room_id)
    blockers = await _has_child_or_business_refs(db, room_id=room_id)
    if blockers:
        raise BusinessRuleError(
            "房间存在下级资源或业务关联，不允许删除，可改为停用：" + "；".join(blockers)
        )
    snapshot = _room_out(room)
    await db.delete(room)
    await audit_service.write_audit(
        db,
        action="dorm_room.delete",
        resource_type="dorm_room",
        resource_id=room_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=snapshot,
    )
    await db.commit()
    return {"deleted": True, "id": room_id}


async def delete_floor(
    db: AsyncSession,
    floor_id: int,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    floor = await _load_floor(db, floor_id)
    blockers = await _has_child_or_business_refs(db, floor_id=floor_id)
    if blockers:
        raise BusinessRuleError(
            "楼层存在下级资源或业务关联，不允许删除，可改为停用：" + "；".join(blockers)
        )
    await db.delete(floor)
    await audit_service.write_audit(
        db,
        action="dorm_floor.delete",
        resource_type="dorm_floor",
        resource_id=floor_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data={"id": floor_id},
    )
    await db.commit()
    return {"deleted": True, "id": floor_id}


async def delete_building(
    db: AsyncSession,
    building_id: int,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    building = await _load_building(db, building_id)
    blockers = await _has_child_or_business_refs(db, building_id=building_id)
    if blockers:
        raise BusinessRuleError(
            "楼栋存在下级资源或业务关联，不允许删除，可改为停用：" + "；".join(blockers)
        )
    await db.delete(building)
    await audit_service.write_audit(
        db,
        action="dorm_building.delete",
        resource_type="dorm_building",
        resource_id=building_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data={"id": building_id},
    )
    await db.commit()
    return {"deleted": True, "id": building_id}


async def delete_area(
    db: AsyncSession,
    area_id: int,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    area = await _load_area(db, area_id)
    blockers = await _has_child_or_business_refs(db, area_id=area_id)
    if blockers:
        raise BusinessRuleError(
            "区域存在下级资源或业务关联，不允许删除，可改为停用：" + "；".join(blockers)
        )
    await db.delete(area)
    await audit_service.write_audit(
        db,
        action="dorm_area.delete",
        resource_type="dorm_area",
        resource_id=area_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data={"id": area_id},
    )
    await db.commit()
    return {"deleted": True, "id": area_id}


async def migrate_access_code_keys(
    db: AsyncSession,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
    limit: int = 500,
) -> dict:
    """Re-encrypt room access codes under the current primary key.

    Used after key rotation / separating ACCESS_CODE_ENCRYPTION_KEY from SECRET_KEY.
    Never logs or returns plaintext codes. Undecryptable tokens are counted only.
    """
    from app.core.security import (
        access_code_needs_reencrypt,
        reencrypt_access_code_token,
    )

    rows = (
        await db.execute(
            select(DormRoom)
            .where(DormRoom.access_code_encrypted.is_not(None))
            .with_for_update()
            .limit(limit)
        )
    ).scalars().all()

    migrated = 0
    already_current = 0
    failed = 0
    for room in rows:
        token = room.access_code_encrypted
        if not token:
            continue
        if not access_code_needs_reencrypt(token):
            already_current += 1
            continue
        try:
            room.access_code_encrypted = reencrypt_access_code_token(token)
            migrated += 1
        except Exception:  # noqa: BLE001 — do not leak token/plaintext
            failed += 1

    await audit_service.write_audit(
        db,
        action="dorm_room.access_code.rotate_keys",
        resource_type="dorm_room",
        resource_id=0,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={
            "migrated": migrated,
            "already_current": already_current,
            "failed": failed,
            "scanned": len(rows),
        },
    )
    await db.commit()
    return {
        "migrated": migrated,
        "already_current": already_current,
        "failed": failed,
        "scanned": len(rows),
    }


async def delete_room_type(
    db: AsyncSession,
    type_id: int,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """FIX-010: hard-delete room type only when no room references it.

    Referenced types must be disabled (archived) instead — historical rooms
    keep showing their original type code/name mapping is preserved on room.
    """
    row = (
        await db.execute(
            select(DormRoomType).where(DormRoomType.id == type_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFound(f"Room type {type_id} not found")
    ref_count = (
        await db.execute(
            select(func.count()).select_from(DormRoom).where(DormRoom.room_type == row.type_code)
        )
    ).scalar_one()
    if ref_count:
        raise BusinessRuleError(
            f"房型「{row.type_name}」仍被 {ref_count} 个房间引用，不允许删除，可改为停用"
        )
    snapshot = _room_type_out(row)
    await db.delete(row)
    await audit_service.write_audit(
        db,
        action="dorm_room_type.delete",
        resource_type="dorm_room_type",
        resource_id=type_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=snapshot,
    )
    await db.commit()
    return {"deleted": True, "id": type_id}
