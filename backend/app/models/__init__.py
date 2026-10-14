"""SQLAlchemy ORM models package."""

from app.models.accommodation import (
    AccommodationApplication,
    AccommodationRecord,
    BedReservation,
    CheckoutRecord,
    TransferRecord,
)
from app.models.audit import AuditLog
from app.models.base import Base, TimestampMixin
from app.models.data_scope import SysUserDepartment
from app.models.department import Department
from app.models.dorm import DormArea, DormBed, DormBuilding, DormFloor, DormRoom
from app.models.employee import Employee
from app.models.import_job import ImportJob
from app.models.rbac import SysPermission, SysRole, SysRolePermission
from app.models.user import AuthRefreshToken, SysUser, SysUserRole
from app.models.workflow import (
    EmployeeStatusEvent,
    Notification,
    WorkflowAlert,
    WorkflowTodo,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "SysUser",
    "SysRole",
    "SysPermission",
    "SysUserRole",
    "SysRolePermission",
    "SysUserDepartment",
    "AuthRefreshToken",
    "AuditLog",
    "Department",
    "Employee",
    "DormArea",
    "DormBuilding",
    "DormFloor",
    "DormRoom",
    "DormBed",
    "ImportJob",
    "AccommodationApplication",
    "BedReservation",
    "AccommodationRecord",
    "TransferRecord",
    "CheckoutRecord",
    "EmployeeStatusEvent",
    "WorkflowTodo",
    "WorkflowAlert",
    "Notification",
]
