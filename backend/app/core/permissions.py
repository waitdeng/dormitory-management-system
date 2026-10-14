"""Permission codes and role defaults.

Codes follow spec section 8. Frontend and backend must stay in sync.
"""

from __future__ import annotations

from typing import Final

# ---- Permission codes (spec §8) ----
PERM_EMPLOYEE_VIEW: Final = "employee:view"
PERM_EMPLOYEE_CREATE: Final = "employee:create"
PERM_EMPLOYEE_UPDATE: Final = "employee:update"
PERM_EMPLOYEE_IMPORT: Final = "employee:import"
PERM_EMPLOYEE_EXPORT: Final = "employee:export"
PERM_EMPLOYEE_OFFBOARD: Final = "employee:offboard"

PERM_DORM_VIEW: Final = "dorm:view"
PERM_DORM_CREATE: Final = "dorm:create"
PERM_DORM_UPDATE: Final = "dorm:update"
PERM_BED_MANAGE: Final = "bed:manage"

PERM_CHECKIN_VIEW: Final = "checkin:view"
PERM_CHECKIN_CREATE: Final = "checkin:create"
PERM_CHECKIN_APPROVE: Final = "checkin:approve"
PERM_CHECKIN_ALLOCATE: Final = "checkin:allocate"
PERM_CHECKIN_CONFIRM: Final = "checkin:confirm"

PERM_TRANSFER_VIEW: Final = "transfer:view"
PERM_TRANSFER_CREATE: Final = "transfer:create"
PERM_TRANSFER_COMPLETE: Final = "transfer:complete"

PERM_CHECKOUT_VIEW: Final = "checkout:view"
PERM_CHECKOUT_CREATE: Final = "checkout:create"
PERM_CHECKOUT_INSPECT: Final = "checkout:inspect"
PERM_CHECKOUT_COMPLETE: Final = "checkout:complete"

PERM_REPORT_VIEW: Final = "report:view"
PERM_REPORT_EXPORT: Final = "report:export"

PERM_USER_MANAGE: Final = "user:manage"
PERM_ROLE_MANAGE: Final = "role:manage"
PERM_AUDIT_VIEW: Final = "audit:view"


# ---- Permission catalogue: code -> (name, module, description) ----
PERMISSION_CATALOGUE: Final[dict[str, tuple[str, str, str]]] = {
    PERM_EMPLOYEE_VIEW: ("View employees", "employee", "Query employee profiles"),
    PERM_EMPLOYEE_CREATE: ("Create employees", "employee", "Create employee profiles"),
    PERM_EMPLOYEE_UPDATE: ("Update employees", "employee", "Edit employee profiles"),
    PERM_EMPLOYEE_IMPORT: ("Import employees", "employee", "Excel batch import"),
    PERM_EMPLOYEE_EXPORT: ("Export employees", "employee", "Export employee data"),
    PERM_EMPLOYEE_OFFBOARD: ("Offboard employees", "employee", "Start termination workflow"),
    PERM_DORM_VIEW: ("View dormitories", "dormitory", "Query dorm hierarchy and beds"),
    PERM_DORM_CREATE: (
        "Create dormitories",
        "dormitory",
        "Create areas/buildings/floors/rooms/beds",
    ),
    PERM_DORM_UPDATE: ("Update dormitories", "dormitory", "Edit dorm hierarchy"),
    PERM_BED_MANAGE: ("Manage beds", "dormitory", "Enable/disable beds"),
    PERM_CHECKIN_VIEW: ("View check-in", "checkin", "Query check-in applications"),
    PERM_CHECKIN_CREATE: ("Create check-in", "checkin", "Create check-in applications"),
    PERM_CHECKIN_APPROVE: ("Approve check-in", "checkin", "Approve or reject applications"),
    PERM_CHECKIN_ALLOCATE: ("Allocate beds", "checkin", "Reserve beds for check-in"),
    PERM_CHECKIN_CONFIRM: ("Confirm check-in", "checkin", "Confirm actual occupancy"),
    PERM_TRANSFER_VIEW: ("View transfers", "transfer", "Query transfer records"),
    PERM_TRANSFER_CREATE: ("Create transfers", "transfer", "Create transfer requests"),
    PERM_TRANSFER_COMPLETE: ("Complete transfers", "transfer", "Confirm transfer execution"),
    PERM_CHECKOUT_VIEW: ("View checkouts", "checkout", "Query checkout records"),
    PERM_CHECKOUT_CREATE: ("Create checkouts", "checkout", "Create checkout requests"),
    PERM_CHECKOUT_INSPECT: ("Inspect checkouts", "checkout", "Record room inspection"),
    PERM_CHECKOUT_COMPLETE: ("Complete checkouts", "checkout", "Confirm checkout and free bed"),
    PERM_REPORT_VIEW: ("View reports", "report", "View accommodation reports"),
    PERM_REPORT_EXPORT: ("Export reports", "report", "Export reports to Excel"),
    PERM_USER_MANAGE: ("Manage users", "system", "Manage backend accounts"),
    PERM_ROLE_MANAGE: ("Manage roles", "system", "Manage roles and permissions"),
    PERM_AUDIT_VIEW: ("View audit logs", "system", "Query audit logs"),
}


# ---- Default role codes ----
ROLE_SUPER_ADMIN: Final = "super_admin"
ROLE_HR: Final = "hr"
ROLE_DORM_ADMIN: Final = "dorm_admin"
ROLE_FINANCE_VIEWER: Final = "finance_viewer"
ROLE_DEPT_MANAGER: Final = "dept_manager"

ROLE_CATALOGUE: Final[dict[str, tuple[str, str]]] = {
    ROLE_SUPER_ADMIN: ("Super Administrator", "Full system access"),
    ROLE_HR: ("HR Specialist", "Employee master data and offboarding"),
    ROLE_DORM_ADMIN: ("Dormitory Administrator", "Dorm resources and occupancy workflow"),
    ROLE_FINANCE_VIEWER: ("Finance Viewer", "Read-only reports within data scope"),
    ROLE_DEPT_MANAGER: ("Department Manager", "Read-only within own department"),
}

# Role -> permission codes (spec §8 matrix)
ROLE_PERMISSIONS: Final[dict[str, tuple[str, ...]]] = {
    ROLE_SUPER_ADMIN: tuple(PERMISSION_CATALOGUE.keys()),
    ROLE_HR: (
        PERM_EMPLOYEE_VIEW,
        PERM_EMPLOYEE_CREATE,
        PERM_EMPLOYEE_UPDATE,
        PERM_EMPLOYEE_IMPORT,
        PERM_EMPLOYEE_EXPORT,
        PERM_EMPLOYEE_OFFBOARD,
        PERM_DORM_VIEW,
        PERM_CHECKIN_VIEW,
        PERM_TRANSFER_VIEW,
        PERM_CHECKOUT_VIEW,
        PERM_REPORT_VIEW,
    ),
    ROLE_DORM_ADMIN: (
        PERM_EMPLOYEE_VIEW,
        PERM_DORM_VIEW,
        PERM_DORM_CREATE,
        PERM_DORM_UPDATE,
        PERM_BED_MANAGE,
        PERM_CHECKIN_VIEW,
        PERM_CHECKIN_CREATE,
        PERM_CHECKIN_APPROVE,
        PERM_CHECKIN_ALLOCATE,
        PERM_CHECKIN_CONFIRM,
        PERM_TRANSFER_VIEW,
        PERM_TRANSFER_CREATE,
        PERM_TRANSFER_COMPLETE,
        PERM_CHECKOUT_VIEW,
        PERM_CHECKOUT_CREATE,
        PERM_CHECKOUT_INSPECT,
        PERM_CHECKOUT_COMPLETE,
        PERM_REPORT_VIEW,
        PERM_REPORT_EXPORT,
    ),
    ROLE_FINANCE_VIEWER: (
        PERM_EMPLOYEE_VIEW,
        PERM_DORM_VIEW,
        PERM_REPORT_VIEW,
        PERM_REPORT_EXPORT,
    ),
    ROLE_DEPT_MANAGER: (
        PERM_EMPLOYEE_VIEW,
        PERM_EMPLOYEE_EXPORT,
        PERM_DORM_VIEW,
        PERM_CHECKIN_VIEW,
        PERM_TRANSFER_VIEW,
        PERM_CHECKOUT_VIEW,
        PERM_REPORT_VIEW,
        PERM_REPORT_EXPORT,
    ),
}


def all_permission_codes() -> list[str]:
    return list(PERMISSION_CATALOGUE.keys())
