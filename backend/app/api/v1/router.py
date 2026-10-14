"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    checkins,
    checkouts,
    dashboard,
    departments,
    dormitories,
    employees,
    health,
    imports,
    offboarding,
    rbac,
    reports,
    scanner,
    transfers,
    users,
    workflow,
)

api_router = APIRouter()

# Health is mounted both under /api/v1 and root via main.py
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(rbac.router)
api_router.include_router(departments.router)
api_router.include_router(employees.router)
api_router.include_router(offboarding.emp_router)
api_router.include_router(offboarding.router)
api_router.include_router(imports.router)
api_router.include_router(dormitories.router)
api_router.include_router(checkins.router)
api_router.include_router(checkins.acc_router)
api_router.include_router(transfers.router)
api_router.include_router(checkouts.router)
api_router.include_router(workflow.router)
api_router.include_router(scanner.router)
api_router.include_router(dashboard.router)
api_router.include_router(reports.router)
