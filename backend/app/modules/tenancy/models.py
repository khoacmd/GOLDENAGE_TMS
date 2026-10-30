import uuid
from datetime import time

from sqlalchemy import ARRAY, ForeignKey, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Danh mục công ty dùng chung - không áp RLS (chỉ system admin quản lý)."""

    __tablename__ = "companies"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))


class CompanySettings(TimestampMixin, Base):
    """Cấu hình vận hành theo công ty (ca giao hàng, cut-over...)."""

    __tablename__ = "company_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    # ISO weekday: 1 = Thứ 2 ... 7 = Chủ nhật. Mặc định Thứ 2 - Thứ 7.
    working_weekdays: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), default=lambda: [1, 2, 3, 4, 5, 6]
    )
    shift_start: Mapped[time] = mapped_column(default=time(7, 0))
    shift_end: Mapped[time] = mapped_column(default=time(19, 0))
    cutover_time: Mapped[time] = mapped_column(default=time(17, 0))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")

    # Quy tắc cho nhân viên giao hàng xác nhận kết quả giao trên mobile.
    confirm_time_rule: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # Được xác nhận sớm/muộn hơn giờ ca bao nhiêu phút.
    confirm_grace_minutes: Mapped[int] = mapped_column(default=60, server_default=text("60"))
    confirm_geofence: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    confirm_radius_m: Mapped[int] = mapped_column(default=300, server_default=text("300"))
    photo_required_success: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    photo_required_failed: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Thao tác ghi nhận khi mất mạng được gửi muộn tối đa bao lâu.
    offline_max_delay_minutes: Mapped[int] = mapped_column(default=240, server_default=text("240"))
