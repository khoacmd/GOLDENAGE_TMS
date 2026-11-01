import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Đích của mã kích hoạt / liên kết Zalo: đúng 1 trong 2 (liên hệ khách hàng hoặc tài xế).
_ONE_TARGET = "num_nonnulls(contact_id, user_id) = 1"


class ActivationCode(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Mã kích hoạt dùng 1 lần do admin công ty cấp để liên kết Zalo (D32). Chỉ lưu hash."""

    __tablename__ = "activation_codes"
    __table_args__ = (CheckConstraint(_ONE_TARGET, name="one_target"),)

    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer_contacts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Tạo lại mã / thu hồi liên kết → mã chưa dùng bị vô hiệu.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class ZaloLink(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Zalo ID (theo ứng dụng) đã kích hoạt cho 1 liên hệ khách hàng hoặc 1 tài xế của công ty."""

    __tablename__ = "zalo_links"
    __table_args__ = (
        CheckConstraint(_ONE_TARGET, name="one_target"),
        # Mỗi đích chỉ 1 liên kết đang hiệu lực (kích hoạt lại → thay liên kết cũ).
        Index(
            "uq_zalo_links_contact_active",
            "contact_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL AND contact_id IS NOT NULL"),
        ),
        Index(
            "uq_zalo_links_user_active",
            "company_id",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL AND user_id IS NOT NULL"),
        ),
    )

    zalo_user_id: Mapped[str] = mapped_column(String(64), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer_contacts.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    display_name: Mapped[str | None] = mapped_column(String(255))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
