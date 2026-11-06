import base64
import uuid
from dataclasses import asdict
from datetime import date
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile, status

from app.core.auth import CompanyAdminDep, CurrentUserDep, ManagerOrAdminDep, OfficeStaffDep
from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import AppError, PermissionDeniedError
from app.core.schemas import Page, PageParams, page_params
from app.modules.integration import dms, service
from app.modules.integration.models import ImportKind, ImportSource
from app.modules.integration.registry import SPECS
from app.modules.integration.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ColumnOut,
    DmsMasterConversionOut,
    DmsOrdersConversionOut,
    ImportJobOut,
    ImportResultOut,
    ImportSpecOut,
    IntegrationRequest,
)
from app.modules.master_data import service as master_data

imports_router = APIRouter(prefix="/imports", tags=["imports"])
api_keys_router = APIRouter(prefix="/api-keys", tags=["integration"])
integration_router = APIRouter(prefix="/integration", tags=["integration"])
conversions_router = APIRouter(prefix="/conversions", tags=["imports"])

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
async def list_specs(_: OfficeStaffDep) -> list[ImportSpecOut]:
    return [_spec_out(kind) for kind in SPECS]


@imports_router.get("/templates/{kind}", response_class=Response)
async def download_template(kind: ImportKind, _: OfficeStaffDep) -> Response:
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
    data = await file.read(get_settings().max_import_bytes + 1)
    if len(data) > get_settings().max_import_bytes:
        raise AppError(
            f"File quá lớn (tối đa {get_settings().max_import_bytes // 1024 // 1024} MB)",
            code="file_too_large",
        )
    raw_rows = service.read_file(data, file.filename or "")
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
    _: OfficeStaffDep, session: DbSession, params: Annotated[PageParams, Depends(page_params)]
) -> Page[ImportJobOut]:
    items, total = await service.list_jobs(session, params)
    return Page(items=[ImportJobOut.model_validate(j) for j in items], total=total)


# --- Chuyển đổi file từ hệ thống ngoài sang template import ----------------------------


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(get_settings().max_import_bytes + 1)
    if len(data) > get_settings().max_import_bytes:
        raise AppError(
            f"File quá lớn (tối đa {get_settings().max_import_bytes // 1024 // 1024} MB)",
            code="file_too_large",
        )
    return data


def _master_out(
    prefix: str, file: UploadFile, content: bytes, summary: dms.MasterSummary
) -> DmsMasterConversionOut:
    stem = PurePath(file.filename or "dms").stem
    return DmsMasterConversionOut(
        filename=f"{prefix}_{stem}.xlsx",
        content_base64=base64.b64encode(content).decode(),
        **asdict(summary),
    )


@conversions_router.post("/dms-customers")
async def convert_dms_customers(
    _: ManagerOrAdminDep,
    session: DbSession,
    file: Annotated[UploadFile, File(description="File đơn hàng tải từ DMS (.xlsx/.csv)")],
) -> DmsMasterConversionOut:
    """Khách hàng trong file DMS chưa có trong hệ thống → template import khách hàng."""
    data = await _read_upload(file)
    name = file.filename or ""
    existing = await master_data.existing_customer_codes(
        session, dms.dms_customer_codes(data, name)
    )
    content, summary = dms.convert_dms_customers(data, name, existing)
    return _master_out("KhachHang", file, content, summary)


@conversions_router.post("/dms-products")
async def convert_dms_products(
    _: ManagerOrAdminDep,
    session: DbSession,
    file: Annotated[UploadFile, File(description="File đơn hàng tải từ DMS (.xlsx/.csv)")],
    product_code_length: Annotated[
        int, Query(ge=0, le=40, description="Độ dài mã hàng sau khi thêm số 0 bên trái; 0 = giữ")
    ] = dms.DEFAULT_PRODUCT_CODE_LENGTH,
) -> DmsMasterConversionOut:
    """Mặt hàng trong file DMS chưa có trong hệ thống → template import mặt hàng."""
    data = await _read_upload(file)
    name = file.filename or ""
    existing = await master_data.existing_product_codes(
        session, dms.dms_product_codes(data, name, product_code_length)
    )
    content, summary = dms.convert_dms_products(
        data, name, existing, product_code_length=product_code_length
    )
    return _master_out("MatHang", file, content, summary)


@conversions_router.post("/dms-orders")
async def convert_dms_orders(
    _: ManagerOrAdminDep,
    file: Annotated[UploadFile, File(description="File đơn hàng tải từ DMS (.xlsx/.csv)")],
    delivery_date: Annotated[
        date | None, Query(description="Ngày giao yêu cầu cho mọi đơn; trống = theo file")
    ] = None,
    product_code_length: Annotated[
        int, Query(ge=0, le=40, description="Độ dài mã hàng sau khi thêm số 0 bên trái; 0 = giữ")
    ] = dms.DEFAULT_PRODUCT_CODE_LENGTH,
) -> DmsOrdersConversionOut:
    data = await _read_upload(file)
    content, summary = dms.convert_dms_orders(
        data,
        file.filename or "",
        delivery_date=delivery_date,
        product_code_length=product_code_length,
    )
    stem = PurePath(file.filename or "dms").stem
    return DmsOrdersConversionOut(
        filename=f"DonHang_{stem}.xlsx",
        content_base64=base64.b64encode(content).decode(),
        **asdict(summary),
    )


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
