"""Owned product records; learning credit remains in the evidence domain."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VacancyAnalysis(Base):
    __tablename__ = "vacancy_analyses"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    source_text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    analyzer_version: Mapped[str] = mapped_column(String(40))
    requirements: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VacancyTarget(Base):
    __tablename__ = "vacancy_targets"
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    vacancy_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("vacancy_analyses.id", ondelete="CASCADE"))
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearnerProject(Base):
    __tablename__ = "learner_projects"
    __table_args__ = (UniqueConstraint("user_id", "template_id", name="uq_project_owner_template"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[str] = mapped_column(String(80))
    template_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectSubmission(Base):
    __tablename__ = "project_submissions"
    __table_args__ = (UniqueConstraint("project_id", "idempotency_key", name="uq_project_submission_idempotency"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("learner_projects.id", ondelete="CASCADE"), index=True)
    milestone_id: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    artifact_text: Mapped[str] = mapped_column(Text)
    repository_url: Mapped[str | None] = mapped_column(String(2048))
    validation: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioEntry(Base):
    __tablename__ = "portfolio_entries"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("learner_projects.id", ondelete="CASCADE"), unique=True)
    public_token: Mapped[str] = mapped_column(String(64), unique=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(String(2000))
    repository_url: Mapped[str | None] = mapped_column(String(2048))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GeneratedPracticeBinding(Base):
    __tablename__ = "generated_practice_bindings"
    step_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_plan_steps.id", ondelete="CASCADE"), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(String(80))
    exercise_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("exercise_versions.id", ondelete="RESTRICT"))


class GeneratedExerciseAttempt(Base):
    __tablename__ = "generated_exercise_attempts"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_generated_attempt_idempotency"),
        CheckConstraint("status IN ('pending', 'reviewed', 'unavailable', 'coding_result')", name="ck_generated_attempt_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    generation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_plan_generations.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_plan_steps.id", ondelete="CASCADE"))
    coding_attempt_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("coding_attempts.id", ondelete="CASCADE"), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    answer: Mapped[str] = mapped_column(Text)
    exercise_snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24))
    feedback: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
