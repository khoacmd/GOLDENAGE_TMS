import uuid
from datetime import date, datetime
from decimal import Decimal
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


# --- Đơn hàng của khách (Zalo Mini App) ---------------------------------------------------


class CustomerOrderStatus(StrEnum):
    WAITING = "WAITING"  # chưa lên lịch giao
    SCHEDULED = "SCHEDULED"  # đã vào lệnh được duyệt, xe chưa xuất phát
    IN_TRANSIT = "IN_TRANSIT"  # xe đang giao
    PARTIAL = "PARTIAL"  # đã giao một phần (đơn có hàng khô + lạnh đi riêng)
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"  # lần giao gần nhất không thành công, chờ giao lại
    CANCELLED = "CANCELLED"


class DeliveryAttemptStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class CustomerEta(BaseModel):
    """Khoảng giờ hàng đến dự kiến."""

    earliest: datetime
    latest: datetime


class CustomerOrderSummary(BaseModel):
    id: uuid.UUID
    external_ref: str
    customer_code: str
    customer_name: str
    delivery_point_code: str
    delivery_point_name: str | None
    delivery_address: str
    requested_date: date
    status: CustomerOrderStatus
    # Chỉ liên hệ chủ thấy giá trị đơn; liên hệ điểm giao nhận None.
    can_see_value: bool
    order_value: Decimal | None
    line_count: int
    delivered_at: datetime | None  # lần giao thành công gần nhất
    eta: CustomerEta | None  # chỉ khi đơn đang giao (sớm nhất nếu các phần đi xe khác nhau)


class CustomerOrderList(BaseModel):
    date: date
    items: list[CustomerOrderSummary]


class CustomerOrderLine(BaseModel):
    product_code: str
    product_name: str
    uom: str
    qty: Decimal
    amount: Decimal | None  # None với liên hệ điểm giao


class DriverContact(BaseModel):
    name: str
    phone: str | None  # Zalo của tài xế = số điện thoại (mở qua zalo.me/<sđt>)
    is_assistant: bool


class CustomerDeliveryAttempt(BaseModel):
    """Một lượt giao (1 phần đơn trên 1 chuyến đã duyệt)."""

    trip_code: str
    plan_date: date
    temp_group: str  # DRY / COLD
    status: DeliveryAttemptStatus
    dispatched_at: datetime | None
    eta: CustomerEta | None  # chỉ khi đang giao
    delivered_at: datetime | None
    reason: str | None
    driver_name: str | None
    # Chỉ khi chuyến đang giao (còn đơn chưa giao); kết thúc chuyến thì không còn hiện.
    driver_contacts: list[DriverContact]
    photo_urls: list[str]


class CustomerOrderDetail(CustomerOrderSummary):
    note: str | None
    lines: list[CustomerOrderLine]
    deliveries: list[CustomerDeliveryAttempt]


class RoutePoint(BaseModel):
    latitude: float
    longitude: float


class CustomerRoute(BaseModel):
    """Tuyến xe đã đi trên 1 chuyến của đơn; chỉ có kho và điểm giao của khách là tọa độ rõ."""

    trip_code: str
    warehouse: RoutePoint
    destination: RoutePoint  # điểm giao của khách
    reached: bool  # xe đã đến điểm của khách (tuyến kết thúc tại đó)
    segments: list[list[tuple[float, float]]]  # các đoạn đường [(kinh độ, vĩ độ)], có thể rỗng
