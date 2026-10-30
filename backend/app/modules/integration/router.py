import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile, status

from app.core.auth import CompanyAdminDep, CurrentUserDep
from app.core.db import DbSession
from app.core.errors import PermissionDeniedError
from app.core.schemas import Page, PageParams, page_params
from app.modules.integration import service
from app.modules.integration.models import ImportKind, ImportSource
from app.modules.integration.registry import SPECS
from app.modules.integration.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ColumnOut,
    ImportJobOut,
    ImportResultOut,
    ImportSpecOut,
    IntegrationRequest,
)

imports_router = APIRouter(prefix="/imports", tags=["imports"])
api_keys_router = APIRouter(prefix="/api-keys", tags=["integration"])
integration_router = APIRouter(prefix="/integration", tags=["integration"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _spec_out(kind: ImportKind) -> ImportSpecOut:
    spec = SPECS[kind]
    return ImportSpecOut(
        kind=kind,
        title=spec.title,
        description=spec.description,
        columns=[ColumnOut(**c.__dict__) for c in spec.columns],
    )


@imports_router.get("/specs")
async def list_specs(_: CurrentUserDep) -> list[ImportSpecOut]:
    return [_spec_out(kind) for kind in SPECS]


@imports_router.get("/templates/{kind}", response_class=Response)
async def download_template(kind: ImportKind, _: CurrentUserDep) -> Response:
    content = service.build_template(SPECS[kind])
    return Response(
        content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="tms-template-{kind.value}.xlsx"'},
    )


@imports_router.post("/{kind}")
async def import_file(
    kind: ImportKind,
    user: CurrentUserDep,
    session: DbSession,
    file: Annotated[UploadFile, File(description="File .xlsx hoặc .csv theo template")],
    dry_run: Annotated[bool, Query(description="Chỉ kiểm tra, không ghi dữ liệu")] = False,
) -> ImportResultOut:
    spec = SPECS[kind]
    if user.company_id is None or not user.has_any_role(*spec.allowed_roles):
        raise PermissionDeniedError(f"Không có quyền import {spec.title.lower()}")
    raw_rows = service.read_file(await file.read(), file.filename or "")
    result = await service.run_import(
        session,
        spec,
        raw_rows,
        company_id=user.cid,
        source=ImportSource.FILE,
        dry_run=dry_run,
        filename=file.filename,
        actor_id=user.id,
    )
    await session.commit()
    return result


@imports_router.get("/jobs")
async def list_jobs(
    user: CurrentUserDep, session: DbSession, params: Annotated[PageParams, Depends(page_params)]
) -> Page[ImportJobOut]:
    _ = user.cid
    items, total = await service.list_jobs(session, params)
    return Page(items=[ImportJobOut.model_validate(j) for j in items], total=total)


# --- API key (admin công ty) --------------------------------------------------------------


@api_keys_router.get("")
async def list_api_keys(_: CompanyAdminDep, session: DbSession) -> list[ApiKeyOut]:
    return [ApiKeyOut.model_validate(k) for k in await service.list_api_keys(session)]


@api_keys_router.post("", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate, user: CompanyAdminDep, session: DbSession
) -> ApiKeyCreated:
    api_key, plain = await service.create_api_key(session, user.cid, body.name, user.id)
    await session.commit()
    return ApiKeyCreated(**ApiKeyOut.model_validate(api_key).model_dump(), api_key=plain)


@api_keys_router.post("/{key_id}/revoke")
async def revoke_api_key(key_id: uuid.UUID, _: CompanyAdminDep, session: DbSession) -> ApiKeyOut:
    api_key = await service.revoke_api_key(session, key_id)
    await session.commit()
    return ApiKeyOut.model_validate(api_key)


# --- API tích hợp cho hệ thống ngoài (xác thực bằng X-API-Key) ------------------------------


@integration_router.post("/{kind}")
async def integration_import(
    kind: ImportKind,
    body: IntegrationRequest,
    session: DbSession,
    x_api_key: Annotated[str, Header(description="API key do admin công ty cấp")],
) -> ImportResultOut:
    api_key = await service.authenticate_api_key(session, x_api_key)
    result = await service.run_import(
        session,
        SPECS[kind],
        [(i, row) for i, row in enumerate(body.rows, start=1)],
        company_id=api_key.company_id,
        source=ImportSource.API,
        dry_run=body.dry_run,
        api_key_id=api_key.id,
    )
    await session.commit()
    return result
