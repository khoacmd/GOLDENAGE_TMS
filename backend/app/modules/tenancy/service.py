import base64
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import set_tenant_context
from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.identity import service as identity_service
from app.modules.identity.models import CompanyRole
from app.modules.tenancy.models import Company, CompanySettings
from app.modules.tenancy.schemas import (
    CompanyCreate,
    CompanySettingsUpdate,
    CompanyUpdate,
    PrintProfileOut,
    PrintTemplates,
)


async def list_companies(session: AsyncSession) -> list[Company]:
    return list(await session.scalars(select(Company).order_by(Company.code)))


async def get_company(session: AsyncSession, company_id: uuid.UUID) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise NotFoundError("Không tìm thấy công ty")
    return company


async def create_company(
    session: AsyncSession, data: CompanyCreate, *, actor_id: uuid.UUID
) -> Company:
    code_taken = await session.scalar(
        select(Company.id).where(func.lower(Company.code) == data.code.lower())
    )
    if code_taken is not None:
        raise ConflictError(f"Mã công ty '{data.code}' đã tồn tại")

    company = Company(code=data.code.upper(), name=data.name)
    session.add(company)
    await session.flush()

    # Các bảng theo công ty chịu RLS → chuyển context sang công ty mới trước khi ghi.
    await set_tenant_context(session, company_id=company.id, user_id=actor_id)
    session.add(CompanySettings(company_id=company.id))

    admin = await identity_service.get_user_by_username(session, data.admin.username)
    if admin is None:
        if not data.admin.password or not data.admin.full_name:
            raise AppError("Tạo admin mới cần password và full_name", code="admin_incomplete")
        admin = await identity_service.create_user(
            session,
            username=data.admin.username,
            password=data.admin.password,
            full_name=data.admin.full_name,
            email=data.admin.email,
            home_company_id=company.id,
        )
    await identity_service.grant_role(
        session, company_id=company.id, user_id=admin.id, role=CompanyRole.COMPANY_ADMIN
    )
    await session.flush()
    return company


async def update_company(
    session: AsyncSession, company_id: uuid.UUID, data: CompanyUpdate
) -> Company:
    company = await get_company(session, company_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    await session.flush()
    return company


async def get_settings(session: AsyncSession, company_id: uuid.UUID) -> CompanySettings:
    settings = await session.get(CompanySettings, company_id)
    if settings is None:
        raise NotFoundError("Chưa có cấu hình cho công ty")
    return settings


async def update_settings(
    session: AsyncSession, company_id: uuid.UUID, data: CompanySettingsUpdate
) -> CompanySettings:
    settings = await get_settings(session, company_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    if settings.shift_start >= settings.shift_end:
        raise AppError("Giờ bắt đầu ca phải trước giờ kết thúc", code="invalid_shift")
    await session.flush()
    return settings


# --- Mẫu phiếu in ---------------------------------------------------------------------------

LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_LOGO_BYTES = 512 * 1024


async def print_profile(session: AsyncSession, company_id: uuid.UUID) -> PrintProfileOut:
    settings = await get_settings(session, company_id)
    company = await get_company(session, company_id)
    logo = await session.scalar(
        select(CompanySettings.logo).where(CompanySettings.company_id == company_id)
    )
    return PrintProfileOut(
        company_name=company.name,
        logo=(
            f"data:{settings.logo_content_type};base64,{base64.b64encode(logo).decode()}"
            if logo
            else None
        ),
        **{f: getattr(settings, f) for f in PrintTemplates.model_fields},
    )


async def update_print_templates(
    session: AsyncSession, company_id: uuid.UUID, data: PrintTemplates
) -> None:
    settings = await get_settings(session, company_id)
    for field, value in data.model_dump().items():
        setattr(settings, field, value)
    await session.flush()


async def set_logo(
    session: AsyncSession, company_id: uuid.UUID, data: bytes | None, content_type: str = ""
) -> None:
    """Đặt logo (PNG/JPEG/WebP, tối đa 512 KB); `data=None` = xóa logo."""
    if data is not None:
        if content_type not in LOGO_TYPES:
            raise AppError("Logo phải là ảnh PNG, JPEG hoặc WebP", code="invalid_logo")
        if not data or len(data) > MAX_LOGO_BYTES:
            raise AppError("Logo rỗng hoặc lớn hơn 512 KB", code="invalid_logo")
    settings = await get_settings(session, company_id)
    settings.logo = data
    settings.logo_content_type = content_type if data is not None else None
    await session.flush()
