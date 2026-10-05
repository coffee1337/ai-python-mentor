"""Durable AI admission state; never contains prompts or credentials."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIRequestLease(Base):
    __tablename__ = "ai_request_leases"
    __table_args__ = (
        CheckConstraint("status IN ('processing', 'completed', 'failed')", name="ck_ai_request_lease_status"),
    )

    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    operation: Mapped[str] = mapped_column(String(40), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    lease_token: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AIGenerationInput(Base):
    """Original context identity shared by immutable forced regenerations."""
    __tablename__ = "ai_generation_inputs"

    generation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_plan_generations.id", ondelete="CASCADE"), primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class AICallReservation(Base):
    __tablename__ = "ai_call_reservations"
    __table_args__ = (
        CheckConstraint("reserved_micro_usd >= 0 AND charged_micro_usd >= 0", name="ck_ai_reservation_cost"),
        CheckConstraint("input_chars >= 0", name="ck_ai_reservation_input_size"),
        Index("ix_ai_reservations_user_operation_time", "user_id", "operation", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    request_key: Mapped[str] = mapped_column(String(160), nullable=False)
    lease_token: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_micro_usd: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    charged_micro_usd: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    cost_is_estimate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved", server_default="reserved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
