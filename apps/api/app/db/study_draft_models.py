"""Private unsubmitted work, with a durable revision even after clearing it."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StudyDraft(Base):
    __tablename__ = "study_drafts"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "resource_id", "version", "milestone_id", name="uq_study_draft_identity"),
        CheckConstraint("kind IN ('lesson_flow','coding','reflection','project_milestone')", name="ck_study_draft_kind"),
        CheckConstraint("revision >= 1", name="ck_study_draft_revision"),
        CheckConstraint(
            "(kind = 'project_milestone' AND version = 0 AND milestone_id <> '' AND project_id IS NOT NULL AND exercise_version_id IS NULL) OR "
            "(kind <> 'project_milestone' AND version >= 1 AND milestone_id = '' AND project_id IS NULL AND exercise_version_id IS NOT NULL)",
            name="ck_study_draft_context",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    milestone_id: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("learner_projects.id", ondelete="CASCADE"))
    exercise_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("exercise_versions.id", ondelete="RESTRICT"))
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
