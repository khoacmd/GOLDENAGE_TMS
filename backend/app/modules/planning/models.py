import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type


class RunTrigger(StrEnum):
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class PlanningRun(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Một lần lập kế hoạch tự động; lưu snapshot đầu vào để tái hiện/debug."""

    __tablename__ = "planning_runs"
    __table_args__ = (Index("ix_planning_runs_plan_date", "company_id", "plan_date"),)

    plan_date: Mapped[date]
    trigger: Mapped[RunTrigger] = mapped_column(enum_type(RunTrigger))
    status: Mapped[RunStatus] = mapped_column(enum_type(RunStatus), default=RunStatus.QUEUED)
    # Hủy các lệnh nháp lập tự động trước đó của ngày này rồi lập lại.
    replace_drafts: Mapped[bool] = mapped_column(default=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    distance_source: Mapped[str | None] = mapped_column(String(16))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    unassigned: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(String(2000))
