"""Department data-scope resolution and query helpers (M5 P0).

Full access roles see every department. Scoped roles are limited to
explicitly assigned departments plus departments they manage (and descendants).
An empty allowed set means no employee/occupancy data is visible — deny-by-default.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDenied
from app.core.permissions import ROLE_HR, ROLE_SUPER_ADMIN
from app.models.data_scope import SysUserDepartment
from app.models.department import Department
from app.models.employee import Employee
from app.models.user import SysUser

FULL_ACCESS_ROLES: frozenset[str] = frozenset({ROLE_SUPER_ADMIN, ROLE_HR})


@dataclass(frozen=True)
class DeptScope:
    """Resolved department scope. `department_ids is None` means all."""

    user_id: int
    department_ids: frozenset[int] | None

    @property
    def is_full(self) -> bool:
        return self.department_ids is None

    def allows(self, department_id: int | None) -> bool:
        if self.is_full:
            return True
        if department_id is None:
            return False
        return department_id in self.department_ids  # type: ignore[operator]

    def require(self, department_id: int | None, *, resource: str = "resource") -> None:
        if not self.allows(department_id):
            raise PermissionDenied(f"Access denied: {resource} is outside your department scope")


def _expand_with_descendants(roots: set[int], departments: list[Department]) -> set[int]:
    children: dict[int | None, list[int]] = {}
    for d in departments:
        children.setdefault(d.parent_id, []).append(d.id)
    out = set(roots)
    stack = list(roots)
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


async def resolve_department_scope(
    db: AsyncSession,
    *,
    user_id: int,
    roles: list[str] | set[str],
    employee_id: int | None = None,
) -> DeptScope:
    """Compute the department scope for a principal."""
    role_set = set(roles)
    if role_set & FULL_ACCESS_ROLES:
        return DeptScope(user_id=user_id, department_ids=None)

    departments = (await db.execute(select(Department))).scalars().all()

    assigned = set(
        (
            await db.execute(
                select(SysUserDepartment.department_id).where(
                    SysUserDepartment.user_id == user_id
                )
            )
        ).scalars().all()
    )

    managed: set[int] = set()
    if employee_id is not None:
        managed = {d.id for d in departments if d.manager_employee_id == employee_id}
    # Fallback: profile may not carry employee_id in lightweight principals.
    if not managed and employee_id is None:
        user = (
            await db.execute(select(SysUser).where(SysUser.id == user_id))
        ).scalar_one_or_none()
        if user is not None and user.employee_id is not None:
            managed = {
                d.id for d in departments if d.manager_employee_id == user.employee_id
            }

    roots = assigned | managed
    allowed = _expand_with_descendants(roots, departments) if roots else set()
    return DeptScope(user_id=user_id, department_ids=frozenset(allowed))


async def resolve_for_principal(db: AsyncSession, principal) -> DeptScope:
    """Resolve scope from a CurrentUser-like object (id, roles, optional employee_id)."""
    return await resolve_department_scope(
        db,
        user_id=principal.id,
        roles=principal.roles,
        employee_id=getattr(principal, "employee_id", None),
    )


def filter_employee_ids_subquery(scope: DeptScope):
    """SQLAlchemy subquery of employee ids inside the scope (None → no filter)."""
    if scope.is_full:
        return None
    ids = scope.department_ids or frozenset()
    return select(Employee.id).where(Employee.department_id.in_(ids) if ids else False)


def apply_employee_scope(query, scope: DeptScope, employee_col=None):
    """AND department scope onto an employee-filtered query. Empty scope → no rows."""
    if scope.is_full:
        return query
    col = employee_col if employee_col is not None else Employee.id
    ids = scope.department_ids or frozenset()
    if not ids:
        return query.where(False)
    return query.where(col.in_(select(Employee.id).where(Employee.department_id.in_(ids))))


def apply_employee_department_scope(query, scope: DeptScope, department_col):
    """AND scope onto a query that already joins employees via department_col."""
    if scope.is_full:
        return query
    ids = scope.department_ids or frozenset()
    if not ids:
        return query.where(False)
    return query.where(department_col.in_(ids))
