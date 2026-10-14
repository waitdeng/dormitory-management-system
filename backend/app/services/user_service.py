"""User and role management service."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, ResourceNotFound, ValidationError
from app.core.security import hash_password
from app.models.rbac import SysPermission, SysRole
from app.models.user import SysUser, SysUserRole
from app.schemas.user import UserCreate, UserRolesUpdate, UserUpdate
from app.services import audit_service, auth_service


async def _load_user(db: AsyncSession, user_id: int) -> SysUser:
    stmt = (
        select(SysUser)
        .where(SysUser.id == user_id)
        .options(selectinload(SysUser.roles).selectinload(SysRole.permissions))
        .execution_options(populate_existing=True)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise ResourceNotFound(f"User {user_id} not found")
    return user


def _user_to_out(user: SysUser, department_ids: list[int] | None = None) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "employee_id": user.employee_id,
        "status": user.status,
        "roles": auth_service.collect_roles(user),
        "department_ids": department_ids or [],
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


async def _department_ids_for(db: AsyncSession, user_id: int) -> list[int]:
    from app.models.data_scope import SysUserDepartment

    rows = (
        await db.execute(
            select(SysUserDepartment.department_id)
            .where(SysUserDepartment.user_id == user_id)
            .order_by(SysUserDepartment.department_id)
        )
    ).scalars().all()
    return list(rows)


async def _user_out(db: AsyncSession, user: SysUser) -> dict:
    return _user_to_out(user, await _department_ids_for(db, user.id))


async def list_users(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    query = select(SysUser)
    count_query = select(func.count()).select_from(SysUser)

    if keyword:
        pattern = f"%{keyword}%"
        cond = (SysUser.username.ilike(pattern)) | (SysUser.display_name.ilike(pattern))
        query = query.where(cond)
        count_query = count_query.where(cond)
    if status:
        query = query.where(SysUser.status == status)
        count_query = count_query.where(SysUser.status == status)

    total = (await db.execute(count_query)).scalar_one()
    stmt = (
        query.options(selectinload(SysUser.roles).selectinload(SysRole.permissions))
        .order_by(SysUser.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    users = result.scalars().all()
    out = []
    for u in users:
        out.append(_user_to_out(u, await _department_ids_for(db, u.id)))
    return out, total


async def create_user(
    db: AsyncSession,
    payload: UserCreate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    existing = (
        await db.execute(select(SysUser).where(SysUser.username == payload.username))
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Username '{payload.username}' already exists")

    user = SysUser(
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        employee_id=payload.employee_id,
        status=payload.status,
    )
    db.add(user)
    await db.flush()

    if payload.role_codes:
        await _assign_roles(db, user, payload.role_codes)

    await audit_service.write_audit(
        db,
        action="user.create",
        resource_type="sys_user",
        resource_id=user.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after_data={"username": user.username, "roles": payload.role_codes},
    )
    await db.commit()
    user = await _load_user(db, user.id)
    return await _user_out(db, user)


async def update_user(
    db: AsyncSession,
    user_id: int,
    payload: UserUpdate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    user = await _load_user(db, user_id)
    before = {
        "display_name": user.display_name,
        "status": user.status,
        "employee_id": user.employee_id,
    }

    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.employee_id is not None:
        user.employee_id = payload.employee_id
    if payload.status is not None:
        user.status = payload.status
    if payload.password:
        user.password_hash = hash_password(payload.password)

    if payload.status == "disabled":
        await auth_service.revoke_all_user_tokens(db, user.id)

    await audit_service.write_audit(
        db,
        action="user.update",
        resource_type="sys_user",
        resource_id=user.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data=before,
        after_data={
            "display_name": user.display_name,
            "status": user.status,
            "employee_id": user.employee_id,
        },
    )
    await db.commit()
    user = await _load_user(db, user.id)
    return await _user_out(db, user)


async def _assign_roles(db: AsyncSession, user: SysUser, role_codes: list[str]) -> None:
    # Explicit query — never rely on lazy-loading `user.roles` in async SQLAlchemy
    current_ids = set(
        (
            await db.execute(
                select(SysUserRole.role_id).where(SysUserRole.user_id == user.id)
            )
        ).scalars().all()
    )

    if not role_codes:
        for role_id in current_ids:
            await db.execute(
                SysUserRole.__table__.delete().where(
                    (SysUserRole.user_id == user.id) & (SysUserRole.role_id == role_id)
                )
            )
        await db.flush()
        return

    stmt = select(SysRole).where(SysRole.code.in_(role_codes))
    roles = (await db.execute(stmt)).scalars().all()
    found = {r.code for r in roles}
    missing = [c for c in role_codes if c not in found]
    if missing:
        raise ValidationError(f"Unknown role codes: {', '.join(missing)}")

    target_ids = {r.id for r in roles}

    for role_id in current_ids - target_ids:
        await db.execute(
            SysUserRole.__table__.delete().where(
                (SysUserRole.user_id == user.id) & (SysUserRole.role_id == role_id)
            )
        )
    for role_id in target_ids - current_ids:
        db.add(SysUserRole(user_id=user.id, role_id=role_id))
    await db.flush()


async def set_user_roles(
    db: AsyncSession,
    user_id: int,
    payload: UserRolesUpdate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    user = await _load_user(db, user_id)
    before_roles = auth_service.collect_roles(user)
    await _assign_roles(db, user, payload.role_codes)
    await audit_service.write_audit(
        db,
        action="user.set_roles",
        resource_type="sys_user",
        resource_id=user.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data={"roles": before_roles},
        after_data={"roles": payload.role_codes},
    )
    await db.commit()
    user = await _load_user(db, user.id)
    return await _user_out(db, user)


async def set_user_departments(
    db: AsyncSession,
    user_id: int,
    department_ids: list[int],
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
) -> dict:
    """Replace the explicit department data-scope for a user."""
    from app.models.data_scope import SysUserDepartment
    from app.models.department import Department

    user = await _load_user(db, user_id)
    before = await _department_ids_for(db, user.id)

    unique_ids = sorted({int(x) for x in department_ids})
    if unique_ids:
        found = set(
            (
                await db.execute(
                    select(Department.id).where(Department.id.in_(unique_ids))
                )
            ).scalars().all()
        )
        missing = [i for i in unique_ids if i not in found]
        if missing:
            raise ValidationError(f"Unknown department ids: {missing}")

    await db.execute(
        SysUserDepartment.__table__.delete().where(SysUserDepartment.user_id == user.id)
    )
    for dept_id in unique_ids:
        db.add(SysUserDepartment(user_id=user.id, department_id=dept_id))
    await db.flush()

    await audit_service.write_audit(
        db,
        action="user.set_departments",
        resource_type="sys_user",
        resource_id=user.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before_data={"department_ids": before},
        after_data={"department_ids": unique_ids},
    )
    await db.commit()
    user = await _load_user(db, user.id)
    return await _user_out(db, user)


async def list_roles(db: AsyncSession) -> list[dict]:
    stmt = select(SysRole).options(selectinload(SysRole.permissions)).order_by(SysRole.id)
    roles = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "description": r.description,
            "status": r.status,
            "permissions": sorted(p.code for p in r.permissions),
        }
        for r in roles
    ]


async def list_permissions(db: AsyncSession) -> list[dict]:
    stmt = select(SysPermission).order_by(SysPermission.module, SysPermission.id)
    perms = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "module": p.module,
            "description": p.description,
        }
        for p in perms
    ]
