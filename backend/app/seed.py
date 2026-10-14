"""Seed RBAC catalogue and bootstrap admin user.

Run: `python -m app.seed` after migrations.
Credentials come from environment (DMS_ADMIN_*); never hardcoded.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.permissions import PERMISSION_CATALOGUE, ROLE_CATALOGUE, ROLE_PERMISSIONS
from app.core.security import hash_password
from app.models.rbac import SysPermission, SysRole, SysRolePermission
from app.models.user import SysUser, SysUserRole


async def seed_rbac() -> None:
    async with AsyncSessionLocal() as db:
        for code, (name, module, description) in PERMISSION_CATALOGUE.items():
            existing = (
                await db.execute(select(SysPermission).where(SysPermission.code == code))
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    SysPermission(code=code, name=name, module=module, description=description)
                )
        await db.flush()

        perm_map: dict[str, int] = {}
        for row in (await db.execute(select(SysPermission))).scalars():
            perm_map[row.code] = row.id

        for code, (name, description) in ROLE_CATALOGUE.items():
            role = (
                await db.execute(select(SysRole).where(SysRole.code == code))
            ).scalar_one_or_none()
            if role is None:
                role = SysRole(code=code, name=name, description=description, status="active")
                db.add(role)
                await db.flush()

            wanted = set(ROLE_PERMISSIONS.get(code, ()))
            existing_links = {
                r.permission_id
                for r in (
                    await db.execute(
                        select(SysRolePermission).where(SysRolePermission.role_id == role.id)
                    )
                ).scalars()
            }
            for perm_code in wanted:
                perm_id = perm_map.get(perm_code)
                if perm_id is not None and perm_id not in existing_links:
                    db.add(SysRolePermission(role_id=role.id, permission_id=perm_id))

        await db.commit()
        print("RBAC catalogue seeded.")


async def ensure_admin() -> None:
    username = settings.DMS_ADMIN_USERNAME
    password = settings.DMS_ADMIN_PASSWORD
    if not password:
        print(
            "Skip admin bootstrap: DMS_ADMIN_PASSWORD is empty. "
            "Set it in the environment before first login.",
            file=sys.stderr,
        )
        return

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(SysUser).where(SysUser.username == username))
        ).scalar_one_or_none()
        if user is None:
            user = SysUser(
                username=username,
                password_hash=hash_password(password),
                display_name=settings.DMS_ADMIN_DISPLAY_NAME,
                status="active",
            )
            db.add(user)
            await db.flush()
            print(f"Admin user '{username}' created.")
        else:
            print(f"Admin user '{username}' already exists.")

        super_role = (
            await db.execute(select(SysRole).where(SysRole.code == "super_admin"))
        ).scalar_one_or_none()
        if super_role is not None:
            link = (
                await db.execute(
                    select(SysUserRole).where(
                        SysUserRole.user_id == user.id, SysUserRole.role_id == super_role.id
                    )
                )
            ).scalar_one_or_none()
            if link is None:
                db.add(SysUserRole(user_id=user.id, role_id=super_role.id))
                print("Granted super_admin role.")

        await db.commit()


async def main() -> None:
    if not settings.DMS_ADMIN_PASSWORD:
        os.environ.setdefault("DMS_ADMIN_PASSWORD", "")
    await seed_rbac()
    await ensure_admin()


if __name__ == "__main__":
    asyncio.run(main())
