import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func, text
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
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    is_system_admin: Mapped[bool] = mapped_column(default=False, server_default=text("false"))


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
