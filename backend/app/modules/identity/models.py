import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CompanyRole(StrEnum):
    COMPANY_ADMIN = "company_admin"
    MANAGER = "manager"
    WAREHOUSE_KEEPER = "warehouse_keeper"
    DRIVER = "driver"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tài khoản dùng chung toàn hệ thống; quyền theo công ty nằm ở `user_roles`."""

    __tablename__ = "users"
    __table_args__ = (Index("uq_users_username_lower", func.lower(text("username")), unique=True),)

    username: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    # Lần đổi/đặt lại mật khẩu gần nhất: token cấp trước mốc này bị vô hiệu.
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Mã PIN đăng nhập app mobile do admin công ty đặt; chỉ dùng cho tài khoản chỉ là lái xe.
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    is_system_admin: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Công ty sở hữu tài khoản: chỉ admin công ty này được đổi mật khẩu/khóa tài khoản.
    home_company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )


class UserRole(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", "role"),
        CheckConstraint(
            "role IN (" + ", ".join(f"'{r.value}'" for r in CompanyRole) + ")", name="valid_role"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[CompanyRole] = mapped_column(String(32))
