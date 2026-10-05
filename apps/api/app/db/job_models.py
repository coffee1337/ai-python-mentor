"""Durable coding admission; the dispatcher never executes learner code."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class ExecutionJob(Base):
    __tablename__ = "execution_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key_digest", name="uq_execution_jobs_user_request_key"),
        CheckConstraint("status IN ('queued','running','finished','failed','cancelled','unavailable')", name="ck_execution_jobs_status"),
        Index("ix_execution_jobs_status_created", "status", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    coding_attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("coding_attempts.id", ondelete="CASCADE"), unique=True)
    request_key_digest: Mapped[str] = mapped_column(String(64))
    body_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="queued", server_default="queued")
    claim_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
