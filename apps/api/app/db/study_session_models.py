"""An owned study timer; elapsed time never awards learning evidence."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StudySession(Base):
    __tablename__ = "study_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused', 'completed', 'abandoned')", name="ck_study_session_status"),
        CheckConstraint("revision >= 1", name="ck_study_session_revision"),
        CheckConstraint("accumulated_milliseconds BETWEEN 0 AND 28800000", name="ck_study_session_duration"),
        CheckConstraint("estimated_minutes >= 0 AND target_minutes BETWEEN 0 AND 60", name="ck_study_session_estimate"),
        CheckConstraint("(status IN ('completed', 'abandoned') AND ended_at IS NOT NULL AND last_activity_at IS NULL) OR "
                        "(status IN ('active', 'paused') AND ended_at IS NULL)", name="ck_study_session_end"),
        CheckConstraint("(status = 'active' AND last_activity_at IS NOT NULL) OR "
                        "(status != 'active' AND last_activity_at IS NULL)", name="ck_study_session_segment"),
        Index("ix_study_sessions_owner_started", "user_id", "started_at"),
        Index("uq_study_session_open_owner", "user_id", unique=True,
              sqlite_where=text("status IN ('active', 'paused')"),
              postgresql_where=text("status IN ('active', 'paused')")),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accumulated_milliseconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    focus_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
