"""Import job status and error listing (M2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.permissions import PERM_EMPLOYEE_IMPORT, PERM_EMPLOYEE_VIEW
from app.schemas.employee import EmployeeImportRowResult, ImportJobOut
from app.services import employee_service

router = APIRouter(prefix="/imports", tags=["imports"])

ViewImport = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_VIEW))]
ManageImport = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_IMPORT))]


@router.get("/{import_job_id}", response_model=ImportJobOut)
async def get_import_job(
    import_job_id: int,
    db: DbSession,
    _guard: ManageImport,
) -> ImportJobOut:
    return ImportJobOut(**await employee_service.get_import_job(db, import_job_id))


@router.get("/{import_job_id}/errors", response_model=list[EmployeeImportRowResult])
async def get_import_errors(
    import_job_id: int,
    db: DbSession,
    _guard: ManageImport,
) -> list[EmployeeImportRowResult]:
    rows = await employee_service.get_import_errors(db, import_job_id)
    return [EmployeeImportRowResult(**row) for row in rows]
