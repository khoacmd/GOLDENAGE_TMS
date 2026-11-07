from decimal import Decimal

from sqlalchemy import Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RiverBridge(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Cầu vượt sông - tham số lập kế hoạch cho xe máy. Sông (đường tâm) là dữ liệu dùng chung trong
    `rivers/data/*.json`; mỗi công ty tự quản lý danh sách cầu và mức phạt."""

    __tablename__ = "river_bridges"
    __table_args__ = (UniqueConstraint("company_id", "code"),)

    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    river_code: Mapped[str] = mapped_column(String(32))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    # Chi phí phạt (đồng) mỗi lần xe máy qua cầu, cộng vào hàm mục tiêu; càng lớn càng tránh.
    motorbike_penalty: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
