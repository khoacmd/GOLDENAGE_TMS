import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.identity.models import CompanyRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)
    # Bắt buộc khi user thuộc nhiều công ty.
    company_code: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class CompanyRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class Membership(BaseModel):
    company: CompanyRef
    roles: list[CompanyRole]


class MeResponse(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    is_system_admin: bool
    company: CompanyRef | None
    roles: list[CompanyRole]
    memberships: list[Membership]


class CompanyUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    roles: list[CompanyRole] = Field(min_length=1)


class CompanyUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    # Chỉ áp dụng cho tài khoản thuộc công ty (home company).
    password: str | None = Field(default=None, min_length=8)
    is_active: bool | None = None


class RolesUpdate(BaseModel):
    roles: list[CompanyRole]


class CompanyUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    full_name: str
    email: str | None
    phone: str | None
    is_active: bool
    roles: list[CompanyRole]
