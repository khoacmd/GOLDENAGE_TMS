import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ZaloStatus(StrEnum):
    NOT_INVITED = "NOT_INVITED"  # chưa có mã / mã đã hết hạn
    PENDING = "PENDING"  # đã cấp mã, chờ nhập trên Zalo Mini App
    ACTIVE = "ACTIVE"  # đã liên kết Zalo


class ZaloLinkInfo(BaseModel):
    status: ZaloStatus = ZaloStatus.NOT_INVITED
    display_name: str | None = None  # tên Zalo khi kích hoạt
    activated_at: datetime | None = None
    code_expires_at: datetime | None = None  # hạn của mã đang chờ


class ActivationCodeOut(BaseModel):
    """Mã chỉ hiển thị 1 lần lúc tạo (server chỉ lưu hash)."""

    code: str  # dạng XXXX-XXXX
    expires_at: datetime
    link: str | None  # mở Zalo Mini App kèm mã (dùng làm QR); None nếu chưa cấu hình


class ZaloTarget(BaseModel):
    contact_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


class AccountKind(StrEnum):
    DRIVER = "driver"
    CUSTOMER = "customer"


class CompanyRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class ZaloAccount(BaseModel):
    """Một vai trò Zalo đã liên kết: lái xe hoặc khách hàng của 1 công ty."""

    kind: AccountKind
    company: CompanyRef


class ZaloLoginRequest(BaseModel):
    access_token: str  # từ zmp-sdk getAccessToken()
    # Bắt buộc khi Zalo liên kết nhiều tài khoản (nhiều công ty / vừa lái xe vừa khách hàng).
    company_id: uuid.UUID | None = None
    kind: AccountKind | None = None


class ZaloActivateRequest(BaseModel):
    access_token: str
    code: str


class ZaloRefreshRequest(BaseModel):
    refresh_token: str


class ZaloLoginStatus(StrEnum):
    OK = "ok"
    CHOOSE_ACCOUNT = "choose_account"  # gửi lại kèm company_id + kind
    NOT_LINKED = "not_linked"  # cần nhập mã kích hoạt


class ZaloLoginOut(BaseModel):
    status: ZaloLoginStatus
    zalo_name: str | None = None
    account: ZaloAccount | None = None  # tài khoản đã đăng nhập (status = ok)
    accounts: list[ZaloAccount] = []
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"


class CustomerScope(BaseModel):
    """Phạm vi xem đơn: cả khách hàng (chủ) hoặc 1 điểm giao."""

    customer_id: uuid.UUID
    customer_code: str
    customer_name: str
    delivery_point_id: uuid.UUID | None  # None = chủ: mọi điểm giao + giá trị đơn
    delivery_point_code: str | None
    delivery_point_name: str | None


class CustomerMe(BaseModel):
    zalo_user_id: str
    company: CompanyRef
    scopes: list[CustomerScope]
