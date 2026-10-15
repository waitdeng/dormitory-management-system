"""Employee and Excel import/export endpoints (M2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, get_request_id, require_permission
from app.core.permissions import (
    PERM_EMPLOYEE_CREATE,
    PERM_EMPLOYEE_EXPORT,
    PERM_EMPLOYEE_IMPORT,
    PERM_EMPLOYEE_UPDATE,
    PERM_EMPLOYEE_VIEW,
)
from app.schemas.common import PageEnvelope
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeImportCommitOut,
    EmployeeImportPreviewOut,
    EmployeeOut,
    EmployeeUpdate,
)
from app.services import employee_service
from app.services.data_scope import resolve_for_principal

router = APIRouter(prefix="/employees", tags=["employees"])

ViewEmp = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_VIEW))]
CreateEmp = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_CREATE))]
UpdateEmp = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_UPDATE))]
ImportEmp = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_IMPORT))]
ExportEmp = Annotated[CurrentUser, Depends(require_permission(PERM_EMPLOYEE_EXPORT))]


@router.get("", response_model=PageEnvelope[EmployeeOut])
async def list_employees(
    db: DbSession,
    guard: ViewEmp,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    department_id: int | None = Query(None, ge=1),
    employment_status: str | None = Query(None, max_length=32),
    accommodation_status: str | None = Query(None, max_length=32),
    accommodation_required: bool | None = Query(None),
) -> PageEnvelope[EmployeeOut]:
    scope = await resolve_for_principal(db, guard)
    items, total = await employee_service.list_employees(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        department_id=department_id,
        employment_status=employment_status,
        accommodation_status=accommodation_status,
        accommodation_required=accommodation_required,
        scope=scope,
    )
    return PageEnvelope[EmployeeOut](items=items, total=total, page=page, page_size=page_size)


@router.get("/import/template")
async def download_import_template(db: DbSession, _guard: ImportEmp):
    content = employee_service.build_employee_template()
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="employee_import_template.xlsx"'},
    )


@router.post("/import/preview", response_model=EmployeeImportPreviewOut)
async def import_preview(
    request: Request,
    db: DbSession,
    guard: ImportEmp,
    file: UploadFile = File(...),
) -> EmployeeImportPreviewOut:
    content = await file.read()
    data = await employee_service.preview_employee_import(
        db,
        filename=file.filename or "upload.xlsx",
        content=content,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return EmployeeImportPreviewOut(**data)


@router.post("/import/commit", response_model=EmployeeImportCommitOut)
async def import_commit(
    request: Request,
    db: DbSession,
    guard: ImportEmp,
    import_job_id: int = Query(..., ge=1),
) -> EmployeeImportCommitOut:
    data = await employee_service.commit_employee_import(
        db,
        import_job_id,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return EmployeeImportCommitOut(**data)


@router.get("/export")
async def export_employees(
    db: DbSession,
    guard: ExportEmp,
    keyword: str | None = Query(None, max_length=64),
    department_id: int | None = Query(None, ge=1),
    employment_status: str | None = Query(None, max_length=32),
):
    scope = await resolve_for_principal(db, guard)
    content = await employee_service.export_employees(
        db,
        keyword=keyword,
        department_id=department_id,
        employment_status=employment_status,
        scope=scope,
    )
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="employees_export.xlsx"'},
    )


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: int,
    db: DbSession,
    guard: ViewEmp,
) -> EmployeeOut:
    scope = await resolve_for_principal(db, guard)
    return EmployeeOut(**await employee_service.get_employee(db, employee_id, scope=scope))


@router.get("/{employee_id}/accommodation")
async def get_employee_accommodation(
    employee_id: int,
    db: DbSession,
    guard: ViewEmp,
):
    scope = await resolve_for_principal(db, guard)
    return await employee_service.get_employee_accommodation(db, employee_id, scope=scope)


@router.get("/{employee_id}/history")
async def get_employee_history(
    employee_id: int,
    db: DbSession,
    guard: ViewEmp,
):
    scope = await resolve_for_principal(db, guard)
    return await employee_service.get_employee_history(db, employee_id, scope=scope)


@router.post("", response_model=EmployeeOut, status_code=201)
async def create_employee(
    payload: EmployeeCreate,
    request: Request,
    db: DbSession,
    guard: CreateEmp,
) -> EmployeeOut:
    data = await employee_service.create_employee(
        db,
        payload,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return EmployeeOut(**data)


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    request: Request,
    db: DbSession,
    guard: UpdateEmp,
) -> EmployeeOut:
    data = await employee_service.update_employee(
        db,
        employee_id,
        payload,
        actor_user_id=guard.id,
        request_id=get_request_id(request),
    )
    return EmployeeOut(**data)
