import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core.auth import (
    CompanyAdminDep,
    CurrentUser,
    OfficeStaffDep,
    SystemAdminDep,
    require_roles,
)
from app.core.db import DbSession
from app.modules.identity.models import CompanyRole
from app.modules.tenancy import service
from app.modules.tenancy.schemas import (
    CompanyCreate,
    CompanyOut,
    CompanySettingsOut,
    CompanySettingsUpdate,
    CompanyUpdate,
    PrintProfileOut,
    PrintTemplates,
)

admin_router = APIRouter(prefix="/admin/companies", tags=["system-admin"])
company_router = APIRouter(prefix="/company", tags=["company"])


@admin_router.get("")
async def list_companies(_: SystemAdminDep, session: DbSession) -> list[CompanyOut]:
    return [CompanyOut.model_validate(c) for c in await service.list_companies(session)]


@admin_router.post("", status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreate, admin: SystemAdminDep, session: DbSession
) -> CompanyOut:
    company = await service.create_company(session, body, actor_id=admin.id)
    await session.commit()
    return CompanyOut.model_validate(company)


@admin_router.patch("/{company_id}")
async def update_company(
    company_id: uuid.UUID, body: CompanyUpdate, _: SystemAdminDep, session: DbSession
) -> CompanyOut:
    company = await service.update_company(session, company_id, body)
    await session.commit()
    return CompanyOut.model_validate(company)


@company_router.get("/settings")
async def get_company_settings(
    current: Annotated[
        CurrentUser,
        Depends(require_roles(CompanyRole.COMPANY_ADMIN, CompanyRole.MANAGER)),
    ],
    session: DbSession,
) -> CompanySettingsOut:
    settings = await service.get_settings(session, current.cid)
    return CompanySettingsOut.model_validate(settings)


@company_router.put("/settings")
async def update_company_settings(
    body: CompanySettingsUpdate, current: CompanyAdminDep, session: DbSession
) -> CompanySettingsOut:
    settings = await service.update_settings(session, current.cid, body)
    await session.commit()
    return CompanySettingsOut.model_validate(settings)


@company_router.get("/print-profile")
async def get_print_profile(current: OfficeStaffDep, session: DbSession) -> PrintProfileOut:
    """Logo + đầu/chân trang dùng khi in phiếu soạn hàng, phiếu giao hàng."""
    return await service.print_profile(session, current.cid)


@company_router.put("/print-profile")
async def update_print_profile(
    body: PrintTemplates, current: CompanyAdminDep, session: DbSession
) -> PrintProfileOut:
    await service.update_print_templates(session, current.cid, body)
    await session.commit()
    return await service.print_profile(session, current.cid)


@company_router.put("/logo")
async def upload_logo(
    current: CompanyAdminDep,
    session: DbSession,
    file: Annotated[UploadFile, File(description="Logo PNG/JPEG/WebP, tối đa 512 KB")],
) -> PrintProfileOut:
    data = await file.read(service.MAX_LOGO_BYTES + 1)
    await service.set_logo(session, current.cid, data, file.content_type or "")
    await session.commit()
    return await service.print_profile(session, current.cid)


@company_router.delete("/logo")
async def delete_logo(current: CompanyAdminDep, session: DbSession) -> PrintProfileOut:
    await service.set_logo(session, current.cid, None)
    await session.commit()
    return await service.print_profile(session, current.cid)
