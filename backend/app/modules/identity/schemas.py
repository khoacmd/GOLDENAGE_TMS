import uuid

from pydantic import BaseModel, ConfigDict, Field

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
