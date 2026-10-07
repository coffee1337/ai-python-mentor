"""Database models for the first authenticated learning flow."""

from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Float,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    Uuid,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Register extension tables for create_all, Alembic and privacy traversal.
from app.db import account_models, domain_models, job_models, product_models, reflection_models, study_draft_models, study_session_models  # noqa: F401


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    profile: Mapped[Optional["Profile"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    goal: Mapped[Optional["Goal"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    experience_level: Mapped[Optional[str]] = mapped_column(String(32))
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="profile")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    target_role: Mapped[str] = mapped_column(String(120), nullable=False)
    weekly_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=180, server_default="180")
    motivation: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="goal")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="sessions")


class LessonCompletion(Base):
    """Completion evidence only; not a claim of independent mastery."""

    __tablename__ = "lesson_completions"

    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    lesson_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    answer: Mapped[str] = mapped_column(String(200), nullable=False)
    exercise_version_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("exercise_versions.id", ondelete="RESTRICT"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False, default="authored_quiz_correct")
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LessonSession(Base):
    """Opaque pending GET/POST binding to the lesson shown to this learner."""

    __tablename__ = "lesson_sessions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    lesson_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    exercise_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("exercise_versions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_lesson_session_pending", "user_id", "lesson_id", unique=True,
            sqlite_where=consumed_at.is_(None), postgresql_where=consumed_at.is_(None),
        ),
    )


class MentorConversation(Base):
    __tablename__ = "mentor_conversations"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_mentor_user_lesson"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    lesson_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class MentorMessage(Base):
    __tablename__ = "mentor_messages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("mentor_conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed", server_default="completed")
    reply_to_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("mentor_messages.id", ondelete="CASCADE"), unique=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CodingAttempt(Base):
    __tablename__ = "coding_attempts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    exercise_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    # Legacy attempts may lack a trustworthy version; new attempts are bound
    # to the exact immutable ExerciseVersion used for dispatch.
    exercise_version_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    submission_result: Mapped[Optional["SubmissionResult"]] = relationship(
        back_populates="coding_attempt",
        uselist=False,
        cascade="all, delete-orphan",
    )


class SubmissionResult(Base):
    """Normalized terminal result for one CodingAttempt.

    Per-test rows retain only an ordinal, visibility, and outcome; they never
    contain authored test source, names, or raw hidden-test output. This is
    persistence only, not learning evidence: coding evidence remains disabled
    until a separate verified Runner/evidence contract is implemented.
    """

    __tablename__ = "submission_results"
    __table_args__ = (
        UniqueConstraint("coding_attempt_id", name="uq_submission_results_coding_attempt"),
        UniqueConstraint("idempotency_key", name="uq_submission_results_idempotency_key"),
        CheckConstraint(
            "status IN ('finished', 'passed', 'failed', 'timeout', "
            "'resource_violation', 'error', 'runner_error', 'unavailable')",
            name="ck_submission_results_status",
        ),
        CheckConstraint(
            "tests_passed >= 0 AND tests_total >= 0 AND tests_passed <= tests_total",
            name="ck_submission_results_test_counts",
        ),
        CheckConstraint(
            "protocol_version >= 1",
            name="ck_submission_results_protocol_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    coding_attempt_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("coding_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Legacy normalized results may lack a trustworthy version. New results
    # copy the exact version bound to their CodingAttempt.
    exercise_version_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    skill_evidence_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("skill_evidence.id", ondelete="SET NULL"),
        unique=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    protocol_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    tests_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tests_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    timeout: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    resource_violation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    coding_attempt: Mapped[CodingAttempt] = relationship(back_populates="submission_result")
    skill_evidence: Mapped[Optional["SkillEvidence"]] = relationship(
        back_populates="submission_result",
        uselist=False,
    )
    test_results: Mapped[list["SubmissionTestResult"]] = relationship(
        back_populates="submission_result",
        cascade="all, delete-orphan",
        order_by="SubmissionTestResult.test_index",
    )


class SubmissionTestResult(Base):
    """Safe per-test outcome metadata; deliberately has no source/text field."""

    __tablename__ = "submission_test_results"
    __table_args__ = (
        UniqueConstraint(
            "submission_result_id",
            "test_index",
            name="uq_submission_test_results_result_index",
        ),
        CheckConstraint("test_index >= 0", name="ck_submission_test_results_index"),
        CheckConstraint(
            "visibility IN ('public', 'hidden')",
            name="ck_submission_test_results_visibility",
        ),
        CheckConstraint(
            "status IN ('passed', 'failed', 'error', 'not_run')",
            name="ck_submission_test_results_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    submission_result_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("submission_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    test_index: Mapped[int] = mapped_column(Integer, nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    submission_result: Mapped[SubmissionResult] = relationship(back_populates="test_results")


class ExerciseVersion(Base):
    """Immutable ownership boundary for versioned exercise content and hints.

    ``exercise_id`` remains the stable authored exercise identifier used by
    existing LESSONS and coding attempts. A new row is created for every
    published version; existing rows must not be edited in place.
    """

    __tablename__ = "exercise_versions"
    __table_args__ = (
        UniqueConstraint("exercise_id", "version", name="uq_exercise_version"),
        CheckConstraint("version >= 1", name="ck_exercise_version_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    exercise_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    lesson_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    content_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Misconception(Base):
    """Stable key for an authored, versioned misconception catalog entry."""

    __tablename__ = "misconceptions"
    __table_args__ = (
        UniqueConstraint("code", "skill_id", name="uq_misconception_code_skill"),
    )

    code: Mapped[str] = mapped_column(String(120), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MisconceptionVersion(Base):
    """Immutable authored text and remediation for one misconception version."""

    __tablename__ = "misconception_versions"
    __table_args__ = (
        Index("ix_misconception_versions_misconception_code", "misconception_code"),
        UniqueConstraint("misconception_code", "version", name="uq_misconception_version"),
        UniqueConstraint("id", "misconception_code", name="uq_misconception_version_id_code"),
        CheckConstraint("version >= 1", name="ck_misconception_version_positive"),
        CheckConstraint(
            "remediation_exercise_version >= 1",
            name="ck_misconception_remediation_exercise_version_positive",
        ),
        ForeignKeyConstraint(
            ["misconception_code"],
            ["misconceptions.code"],
            name="fk_misconception_versions_code",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    misconception_code: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    error_text: Mapped[str] = mapped_column(Text, nullable=False)
    typical_wrong_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    remediation_text: Mapped[str] = mapped_column(Text, nullable=False)
    remediation_exercise_id: Mapped[str] = mapped_column(String(80), nullable=False)
    remediation_exercise_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MisconceptionMapping(Base):
    """Exact authored wrong-choice mapping for a persisted response source."""

    __tablename__ = "misconception_mappings"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "exercise_id",
            "exercise_version",
            "question_id",
            "wrong_choice",
            name="uq_misconception_mapping_authored_choice",
        ),
        CheckConstraint(
            "source_type IN ('knowledge_check_response', 'assessment_response')",
            name="ck_misconception_mapping_source_type",
        ),
        CheckConstraint("exercise_version >= 1", name="ck_misconception_mapping_exercise_version"),
        ForeignKeyConstraint(
            ["misconception_version_id", "misconception_code"],
            ["misconception_versions.id", "misconception_versions.misconception_code"],
            name="fk_misconception_mapping_version_code",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    exercise_id: Mapped[str] = mapped_column(String(80), nullable=False)
    exercise_version: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[str] = mapped_column(String(100), nullable=False)
    wrong_choice: Mapped[str] = mapped_column(Text, nullable=False)
    misconception_code: Mapped[str] = mapped_column(String(120), nullable=False)
    misconception_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UserMistake(Base):
    """Per-user aggregate; it never changes mastery directly."""

    __tablename__ = "user_mistakes"
    __table_args__ = (
        UniqueConstraint("user_id", "misconception_code", name="uq_user_mistake_user_code"),
        UniqueConstraint(
            "id", "user_id", "misconception_code",
            name="uq_user_mistake_id_user_code",
        ),
        CheckConstraint("occurrence_count >= 1", name="ck_user_mistake_count_positive"),
        CheckConstraint("first_seen_at <= last_seen_at", name="ck_user_mistake_seen_order"),
        ForeignKeyConstraint(
            ["misconception_code", "skill_id"],
            ["misconceptions.code", "misconceptions.skill_id"],
            name="fk_user_mistakes_misconception_skill",
            ondelete="RESTRICT",
        ),
        Index("ix_user_mistakes_user_id", "user_id"),
        Index("ix_user_mistakes_skill_id", "skill_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    misconception_code: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), nullable=False)
    lesson_id: Mapped[Optional[str]] = mapped_column(String(80))
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    last_source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MistakeOccurrence(Base):
    """Idempotent append-only source fact behind a UserMistake aggregate."""

    __tablename__ = "mistake_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            "misconception_code",
            name="uq_mistake_occurrence_source",
        ),
        CheckConstraint(
            "source_type IN ('knowledge_check_response', 'assessment_response', 'coding_attempt')",
            name="ck_mistake_occurrence_source_type",
        ),
        ForeignKeyConstraint(
            ["misconception_code"],
            ["misconceptions.code"],
            name="fk_mistake_occurrences_misconception_code",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["user_mistake_id", "user_id", "misconception_code"],
            ["user_mistakes.id", "user_mistakes.user_id", "user_mistakes.misconception_code"],
            name="fk_mistake_occurrences_user_mistake_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["misconception_version_id", "misconception_code"],
            ["misconception_versions.id", "misconception_versions.misconception_code"],
            name="fk_mistake_occurrences_version_code",
            ondelete="RESTRICT",
        ),
        Index("ix_mistake_occurrences_user_id", "user_id"),
        Index("ix_mistake_occurrences_misconception_code", "misconception_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_mistake_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    misconception_code: Mapped[str] = mapped_column(String(120), nullable=False)
    misconception_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    lesson_id: Mapped[Optional[str]] = mapped_column(String(80))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExerciseHint(Base):
    """One immutable level in an exercise version's five-step hint ladder."""

    __tablename__ = "exercise_hints"
    __table_args__ = (
        UniqueConstraint("exercise_version_id", "level", name="uq_exercise_hint_level"),
        CheckConstraint("level BETWEEN 1 AND 5", name="ck_exercise_hint_level"),
        CheckConstraint(
            "(level = 1 AND kind = 'direction') OR "
            "(level = 2 AND kind = 'concept') OR "
            "(level = 3 AND kind = 'step') OR "
            "(level = 4 AND kind = 'pseudocode') OR "
            "(level = 5 AND kind = 'solution')",
            name="ck_exercise_hint_kind",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    exercise_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class HintReveal(Base):
    """Append-only audit of a user's first reveal of a hint level."""

    __tablename__ = "hint_reveals"
    __table_args__ = (
        UniqueConstraint("user_id", "exercise_version_id", "level", name="uq_hint_reveal_user_version_level"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_hint_reveal_idempotency"),
        CheckConstraint("level BETWEEN 1 AND 5", name="ck_hint_reveal_level"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    exercise_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    hint_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_hints.id", ondelete="RESTRICT"),
        nullable=False,
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    revealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LearningPlan(Base):
    __tablename__ = "learning_plans"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    assessment_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assessment_runs.id", ondelete="SET NULL"), nullable=True)
    focus_skill_id: Mapped[Optional[str]] = mapped_column(String(120))
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

class LearningPlanItem(Base):
    __tablename__ = "learning_plan_items"
    __table_args__ = (UniqueConstraint("plan_id", "lesson_id", name="uq_learning_plan_lesson"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("learning_plans.id", ondelete="CASCADE"), index=True, nullable=False)
    lesson_id: Mapped[str] = mapped_column(String(80), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    focus_score: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)


class CurriculumPlanRevision(Base):
    __tablename__ = "curriculum_plan_revisions"
    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_curriculum_revision_version"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("learning_plans.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False, default="curriculum-v1", server_default="curriculum-v1")
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    goal_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    coverage: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CurriculumSession(Base):
    __tablename__ = "curriculum_sessions"
    __table_args__ = (UniqueConstraint("revision_id", "position", name="uq_curriculum_session_position"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("curriculum_plan_revisions.id", ondelete="CASCADE"), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned", server_default="planned")
    rationale: Mapped[str] = mapped_column(Text, nullable=False)


class CurriculumActivity(Base):
    __tablename__ = "curriculum_activities"
    __table_args__ = (UniqueConstraint("session_id", "position", name="uq_curriculum_activity_position"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("curriculum_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    lesson_id: Mapped[Optional[str]] = mapped_column(String(80))
    skill_id: Mapped[str] = mapped_column(String(120), nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[float] = mapped_column(Float, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    availability: Mapped[str] = mapped_column(String(32), nullable=False, default="available", server_default="available")


class AIPlanGeneration(Base):
    __tablename__ = "ai_plan_generations"
    __table_args__ = (UniqueConstraint("user_id", "input_hash", "model_id", name="uq_ai_plan_cache_key"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    source_revision_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("curriculum_plan_revisions.id", ondelete="SET NULL"))
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready", server_default="ready")
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failure_code: Mapped[Optional[str]] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AIPlanCurrent(Base):
    __tablename__ = "ai_plan_current"

    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    generation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_plan_generations.id", ondelete="CASCADE"), unique=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class AIPlanStep(Base):
    __tablename__ = "ai_plan_steps"
    __table_args__ = (UniqueConstraint("generation_id", "position", name="uq_ai_plan_step_position"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    generation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_plan_generations.id", ondelete="CASCADE"), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    example_code: Mapped[str] = mapped_column(Text, nullable=False)
    exercise_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    submission_type: Mapped[str] = mapped_column(String(20), nullable=False)
    starter_code: Mapped[Optional[str]] = mapped_column(Text)
    constraints: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    success_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    evaluation_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")


class AIUsageLedger(Base):
    __tablename__ = "ai_usage_ledger"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    generation_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_plan_generations.id", ondelete="SET NULL"))
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    output_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

class AssessmentRun(Base):
    __tablename__ = "assessment_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress", server_default="in_progress")
    current_question_id: Mapped[Optional[str]] = mapped_column(String(80))
    current_exercise_version_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    asked_question_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

class AssessmentResponse(Base):
    __tablename__ = "assessment_responses"
    __table_args__ = (UniqueConstraint("run_id", "question_id", name="uq_assessment_run_question"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assessment_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    exercise_version_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    question_id: Mapped[str] = mapped_column(String(80), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), nullable=False)
    difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    answer: Mapped[str] = mapped_column(String(200), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class KnowledgeCheckAttempt(Base):
    __tablename__ = "knowledge_check_attempts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    exercise_version_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    lesson_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class KnowledgeCheckSession(Base):
    """Opaque server-side binding between a learner and one check version."""

    __tablename__ = "knowledge_check_sessions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    lesson_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    exercise_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_knowledge_check_session_pending",
            "user_id",
            "lesson_id",
            unique=True,
            sqlite_where=consumed_at.is_(None),
            postgresql_where=consumed_at.is_(None),
        ),
    )


class KnowledgeCheckResponse(Base):
    __tablename__ = "knowledge_check_responses"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("knowledge_check_attempts.id", ondelete="CASCADE"), index=True, nullable=False)
    question_id: Mapped[str] = mapped_column(String(100), nullable=False)
    answer: Mapped[str] = mapped_column(String(200), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UserSkill(Base):
    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), nullable=False)
    knowledge_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    practice_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    independent_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    retention_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    mastery_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_practiced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class SkillEvidence(Base):
    __tablename__ = "skill_evidence"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_skill_evidence_idempotency"),
        UniqueConstraint(
            "id", "user_id", "skill_id", "source_type",
            name="uq_skill_evidence_identity",
        ),
        CheckConstraint(
            "source_type IN ('assessment_response', 'knowledge_check_attempt', 'coding_attempt', 'review_attempt')",
            name="ck_skill_evidence_source_type",
        ),
        CheckConstraint(
            "(source_type = 'review_attempt' AND retention_only = true) OR "
            "(source_type <> 'review_attempt' AND retention_only = false)",
            name="ck_skill_evidence_retention_only",
        ),
        CheckConstraint("result_score >= 0 AND result_score <= 1", name="ck_skill_evidence_result_score"),
        CheckConstraint("hint_count BETWEEN 0 AND 5", name="ck_skill_evidence_hint_count"),
        CheckConstraint(
            "(assisted = false AND hint_count = 0) OR "
            "(assisted = true AND hint_count > 0)",
            name="ck_skill_evidence_assistance_consistency",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id", ondelete="RESTRICT"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    retention_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    result_score: Mapped[float] = mapped_column(Float, nullable=False)
    assisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    hint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    evidence_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    submission_result: Mapped[Optional["SubmissionResult"]] = relationship(
        back_populates="skill_evidence",
        uselist=False,
    )



class ReviewSession(Base):
    """A version-bound review interaction; due work remains derived from UserSkill."""

    __tablename__ = "review_sessions"
    __table_args__ = (
        UniqueConstraint(
            "id", "user_id", "skill_id", "exercise_version_id", "scheduled_for",
            name="uq_review_session_identity",
        ),
        UniqueConstraint(
            "user_id", "skill_id", "scheduled_for",
            name="uq_review_session_user_skill_day",
        ),
        CheckConstraint(
            "token_hash IS NULL OR length(token_hash) = 64",
            name="ck_review_session_token_hash_length",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    token_hash: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("skills.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    exercise_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    scheduled_for: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ReviewAttempt(Base):
    """Append-only review result, paired with its retention-only SkillEvidence."""

    __tablename__ = "review_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["review_session_id", "user_id", "skill_id", "exercise_version_id", "scheduled_for"],
            [
                "review_sessions.id",
                "review_sessions.user_id",
                "review_sessions.skill_id",
                "review_sessions.exercise_version_id",
                "review_sessions.scheduled_for",
            ],
            name="fk_review_attempt_session_identity",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["skill_evidence_id", "user_id", "skill_id", "evidence_source_type"],
            [
                "skill_evidence.id",
                "skill_evidence.user_id",
                "skill_evidence.skill_id",
                "skill_evidence.source_type",
            ],
            name="fk_review_attempt_evidence_identity",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "evidence_source_type = 'review_attempt'",
            name="ck_review_attempt_evidence_source_type",
        ),
        UniqueConstraint(
            "skill_evidence_id",
            name="uq_review_attempt_skill_evidence_id",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_review_attempt_idempotency"),
        CheckConstraint(
            "applied_on IS NULL OR applied_on >= scheduled_for",
            name="ck_review_attempt_applied_on_not_before_schedule",
        ),
        Index(
            "uq_review_attempt_applied_user_skill_day",
            "user_id",
            "skill_id",
            "applied_on",
            unique=True,
            sqlite_where=text("applied_on IS NOT NULL"),
            postgresql_where=text("applied_on IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    review_session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("skills.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    exercise_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    skill_evidence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="review_attempt", server_default="review_attempt"
    )
    scheduled_for: Mapped[date] = mapped_column(Date, nullable=False)
    applied_on: Mapped[Optional[date]] = mapped_column(Date)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    answers: Mapped[Optional[dict]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SkillMasteryAudit(Base):
    __tablename__ = "skill_mastery_audit"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    evidence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("skill_evidence.id", ondelete="CASCADE"), unique=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id", ondelete="RESTRICT"), index=True, nullable=False)
    before_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    after_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    before_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    after_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1", server_default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    difficulty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default="0.5")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    edges_from: Mapped[list["SkillEdge"]] = relationship(
        foreign_keys="SkillEdge.from_skill_id", back_populates="from_skill", cascade="all, delete-orphan"
    )
    edges_to: Mapped[list["SkillEdge"]] = relationship(
        foreign_keys="SkillEdge.to_skill_id", back_populates="to_skill", cascade="all, delete-orphan"
    )

class SkillEdge(Base):
    __tablename__ = "skill_edges"
    __table_args__ = (
        UniqueConstraint("from_skill_id", "to_skill_id", "relation", name="uq_skill_edge"),
        CheckConstraint("from_skill_id <> to_skill_id", name="ck_skill_edge_not_self"),
        CheckConstraint("relation IN ('prerequisite', 'related', 'specialization')", name="ck_skill_edge_relation"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    from_skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False)
    to_skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    from_skill: Mapped[Skill] = relationship(foreign_keys=[from_skill_id], back_populates="edges_from")
    to_skill: Mapped[Skill] = relationship(foreign_keys=[to_skill_id], back_populates="edges_to")


class LessonSkill(Base):
    __tablename__ = "lesson_skills"
    __table_args__ = (UniqueConstraint("lesson_id", "skill_id", name="uq_lesson_skill"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    lesson_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False)
    skill: Mapped[Skill] = relationship()


class KnowledgeChunk(Base):
    """One retrievable slice of immutable authored lesson theory.

    A chunk is a derived, rebuildable projection of a single immutable
    ``ExerciseVersion`` snapshot. It is scoped to one skill and one content
    version, so retrieval can never surface another skill's material or a
    superseded revision of the lesson the learner is currently seeing.

    Assessed material (the question, its choices, its answer, knowledge-check
    explanations and the hint ladder) is deliberately never chunked: the mentor
    must not be able to read a graded answer out of the index.
    """

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_knowledge_chunks_skill_version", "skill_id", "exercise_version_id"),
        UniqueConstraint(
            "exercise_version_id", "section", "ordinal", name="uq_knowledge_chunk_position",
        ),
        CheckConstraint("ordinal >= 0", name="ck_knowledge_chunk_ordinal"),
        CheckConstraint("char_count > 0 AND char_count <= 4000", name="ck_knowledge_chunk_size"),
        CheckConstraint(
            "section IN ('goal', 'theory', 'body', 'example', 'example_output', "
            "'conclusion', 'practice', 'checkpoint', 'misconception_check')",
            name="ck_knowledge_chunk_section_kind",
        ),
        CheckConstraint(
            "embedding IS NULL OR embedding_dim IS NOT NULL",
            name="ck_knowledge_chunk_embedding_dim",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    exercise_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exercise_versions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    skill_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False,
    )
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # Packed little-endian float32. Kept as opaque bytes so the storage engine
    # never requires pgvector and `alembic upgrade head` still succeeds on a
    # developer machine without the extension installed.
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    embedding_dim: Mapped[Optional[int]] = mapped_column(Integer)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(120))
    embedding_digest: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
