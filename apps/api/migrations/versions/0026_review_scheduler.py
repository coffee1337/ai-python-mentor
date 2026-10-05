"""Add version-bound review sessions and retention-only review evidence."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0026_review_scheduler"
down_revision = "0025_assessment_mistake_mappings"
branch_labels = None
depends_on = None


_BACKUP_EVIDENCE = "review_scheduler_downgrade_evidence"
_BACKUP_AUDIT = "review_scheduler_downgrade_audit"
_BACKUP_SESSIONS = "review_scheduler_downgrade_sessions"
_BACKUP_ATTEMPTS = "review_scheduler_downgrade_attempts"


def _create_downgrade_backups() -> None:
    """Preserve review rows while the previous schema cannot represent them."""

    op.create_table(
        _BACKUP_EVIDENCE,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.Column("retention_only", sa.Boolean(), nullable=False),
        sa.Column("result_score", sa.Float(), nullable=False),
        sa.Column("assisted", sa.Boolean(), nullable=False),
        sa.Column("hint_count", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        _BACKUP_AUDIT,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("evidence_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("before_mastery", sa.Float(), nullable=False),
        sa.Column("after_mastery", sa.Float(), nullable=False),
        sa.Column("before_evidence_count", sa.Integer(), nullable=False),
        sa.Column("after_evidence_count", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        _BACKUP_SESSIONS,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        _BACKUP_ATTEMPTS,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("review_session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_evidence_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("evidence_source_type", sa.String(32), nullable=False),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("applied_on", sa.Date()),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    # Batch mode is required for SQLite's CHECK-constraint replacement. Existing
    # evidence receives the neutral marker default; no rows are otherwise changed.
    with op.batch_alter_table("skill_evidence") as batch_op:
        batch_op.add_column(
            sa.Column(
                "retention_only",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.drop_constraint("ck_skill_evidence_source_type", type_="check")
        batch_op.create_check_constraint(
            "ck_skill_evidence_source_type",
            "source_type IN "
            "('assessment_response', 'knowledge_check_attempt', "
            "'coding_attempt', 'review_attempt')",
        )
        batch_op.create_check_constraint(
            "ck_skill_evidence_retention_only",
            "(source_type = 'review_attempt' AND retention_only = true) OR "
            "(source_type <> 'review_attempt' AND retention_only = false)",
        )
        batch_op.create_unique_constraint(
            "uq_skill_evidence_identity",
            ["id", "user_id", "skill_id", "source_type"],
        )

    op.create_table(
        "review_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["exercise_version_id"],
            ["exercise_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "user_id",
            "skill_id",
            "exercise_version_id",
            "scheduled_for",
            name="uq_review_session_identity",
        ),
        sa.UniqueConstraint(
            "user_id",
            "skill_id",
            "scheduled_for",
            name="uq_review_session_user_skill_day",
        ),
    )
    op.create_index("ix_review_sessions_user_id", "review_sessions", ["user_id"])
    op.create_index("ix_review_sessions_skill_id", "review_sessions", ["skill_id"])
    op.create_index(
        "ix_review_sessions_exercise_version_id",
        "review_sessions",
        ["exercise_version_id"],
    )

    op.create_table(
        "review_attempts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("review_session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_evidence_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "evidence_source_type",
            sa.String(32),
            server_default="review_attempt",
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("applied_on", sa.Date()),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "applied_on IS NULL OR applied_on >= scheduled_for",
            name="ck_review_attempt_applied_on_not_before_schedule",
        ),
        sa.CheckConstraint(
            "evidence_source_type = 'review_attempt'",
            name="ck_review_attempt_evidence_source_type",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["exercise_version_id"],
            ["exercise_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "skill_evidence_id", name="uq_review_attempt_skill_evidence_id"
        ),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_review_attempt_idempotency"
        ),
    )
    op.create_index(
        "ix_review_attempts_review_session_id",
        "review_attempts",
        ["review_session_id"],
    )
    op.create_index("ix_review_attempts_user_id", "review_attempts", ["user_id"])
    op.create_index("ix_review_attempts_skill_id", "review_attempts", ["skill_id"])
    op.create_index(
        "ix_review_attempts_exercise_version_id",
        "review_attempts",
        ["exercise_version_id"],
    )
    op.create_index(
        "uq_review_attempt_applied_user_skill_day",
        "review_attempts",
        ["user_id", "skill_id", "applied_on"],
        unique=True,
        sqlite_where=sa.text("applied_on IS NOT NULL"),
        postgresql_where=sa.text("applied_on IS NOT NULL"),
    )

    # A downgrade keeps review evidence and history in unreferenced backup
    # tables. Restore them on the next upgrade, then remove those backups.
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if _BACKUP_EVIDENCE in tables:
        for table_name, columns in (
            (
                "skill_evidence",
                "id, user_id, skill_id, source_type, source_id, retention_only, "
                "result_score, assisted, hint_count, occurred_at, idempotency_key, "
                "metadata, created_at",
            ),
            (
                "skill_mastery_audit",
                "id, evidence_id, user_id, skill_id, before_mastery, after_mastery, "
                "before_evidence_count, after_evidence_count, policy_version, created_at",
            ),
            (
                "review_sessions",
                "id, user_id, skill_id, exercise_version_id, scheduled_for, created_at, completed_at",
            ),
            (
                "review_attempts",
                "id, review_session_id, user_id, skill_id, exercise_version_id, "
                "skill_evidence_id, evidence_source_type, scheduled_for, applied_on, "
                "idempotency_key, occurred_at, created_at",
            ),
        ):
            backup = {
                "skill_evidence": _BACKUP_EVIDENCE,
                "skill_mastery_audit": _BACKUP_AUDIT,
                "review_sessions": _BACKUP_SESSIONS,
                "review_attempts": _BACKUP_ATTEMPTS,
            }[table_name]
            op.execute(
                sa.text(
                    f"INSERT INTO {table_name} ({columns}) "
                    f"SELECT {columns} FROM {backup}"
                )
            )
        for backup_name in (
            _BACKUP_ATTEMPTS,
            _BACKUP_SESSIONS,
            _BACKUP_AUDIT,
            _BACKUP_EVIDENCE,
        ):
            op.drop_table(backup_name)


def downgrade() -> None:
    # Preserve review-specific rows in temporary, unconstrained tables because
    # the prior schema rejects their evidence source type and marker.
    _create_downgrade_backups()
    op.execute(
        sa.text(
            f"INSERT INTO {_BACKUP_EVIDENCE} "
            "SELECT id, user_id, skill_id, source_type, source_id, retention_only, "
            "result_score, assisted, hint_count, occurred_at, idempotency_key, "
            "metadata, created_at FROM skill_evidence "
            "WHERE source_type = 'review_attempt'"
        )
    )
    op.execute(
        sa.text(
            f"INSERT INTO {_BACKUP_AUDIT} "
            "SELECT id, evidence_id, user_id, skill_id, before_mastery, after_mastery, "
            "before_evidence_count, after_evidence_count, policy_version, created_at "
            "FROM skill_mastery_audit WHERE evidence_id IN "
            "(SELECT id FROM skill_evidence WHERE source_type = 'review_attempt')"
        )
    )
    op.execute(
        sa.text(
            f"INSERT INTO {_BACKUP_SESSIONS} "
            "SELECT id, user_id, skill_id, exercise_version_id, scheduled_for, "
            "created_at, completed_at FROM review_sessions"
        )
    )
    op.execute(
        sa.text(
            f"INSERT INTO {_BACKUP_ATTEMPTS} "
            "SELECT id, review_session_id, user_id, skill_id, exercise_version_id, "
            "skill_evidence_id, evidence_source_type, scheduled_for, applied_on, "
            "idempotency_key, occurred_at, created_at FROM review_attempts"
        )
    )

    op.drop_index(
        "uq_review_attempt_applied_user_skill_day",
        table_name="review_attempts",
    )
    op.drop_index(
        "ix_review_attempts_exercise_version_id",
        table_name="review_attempts",
    )
    op.drop_index("ix_review_attempts_skill_id", table_name="review_attempts")
    op.drop_index("ix_review_attempts_user_id", table_name="review_attempts")
    op.drop_index(
        "ix_review_attempts_review_session_id",
        table_name="review_attempts",
    )
    op.drop_table("review_attempts")
    op.drop_index(
        "ix_review_sessions_exercise_version_id",
        table_name="review_sessions",
    )
    op.drop_index("ix_review_sessions_skill_id", table_name="review_sessions")
    op.drop_index("ix_review_sessions_user_id", table_name="review_sessions")
    op.drop_table("review_sessions")

    op.execute(
        sa.text(
            "DELETE FROM skill_mastery_audit "
            "WHERE evidence_id IN "
            "(SELECT id FROM skill_evidence WHERE source_type = 'review_attempt')"
        )
    )
    op.execute(
        sa.text("DELETE FROM skill_evidence WHERE source_type = 'review_attempt'")
    )

    with op.batch_alter_table("skill_evidence") as batch_op:
        batch_op.drop_constraint(
            "uq_skill_evidence_identity", type_="unique"
        )
        batch_op.drop_constraint(
            "ck_skill_evidence_retention_only", type_="check"
        )
        batch_op.drop_constraint("ck_skill_evidence_source_type", type_="check")
        batch_op.drop_column("retention_only")
        batch_op.create_check_constraint(
            "ck_skill_evidence_source_type",
            "source_type IN "
            "('assessment_response', 'knowledge_check_attempt', 'coding_attempt')",
        )
