import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class InventoryBalance(TenantMixin, Base):
    """Tồn kho dạng snapshot đồng bộ từ hệ thống ngoài (ghi đè theo kho)."""

    __tablename__ = "inventory_balances"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    qty_on_hand: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    synced_at: Mapped[datetime]
