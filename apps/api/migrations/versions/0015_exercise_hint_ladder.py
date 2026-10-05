"""Add immutable exercise versions, hint ladders, and append-only reveals."""

import sqlalchemy as sa
from alembic import op


revision = "0015_exercise_hint_ladder"
down_revision = "0014_ai_usage_ledger_user_index"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "exercise_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("exercise_id", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_exercise_version_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exercise_id", "version", name="uq_exercise_version"),
    )
    op.create_index("ix_exercise_versions_exercise_id", "exercise_versions", ["exercise_id"])
    op.create_index("ix_exercise_versions_lesson_id", "exercise_versions", ["lesson_id"])

    op.create_table(
        "exercise_hints",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("level BETWEEN 1 AND 5", name="ck_exercise_hint_level"),
        sa.CheckConstraint(
            "(level = 1 AND kind = 'direction') OR "
            "(level = 2 AND kind = 'concept') OR "
            "(level = 3 AND kind = 'step') OR "
            "(level = 4 AND kind = 'pseudocode') OR "
            "(level = 5 AND kind = 'solution')",
            name="ck_exercise_hint_kind",
        ),
        sa.ForeignKeyConstraint(["exercise_version_id"], ["exercise_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exercise_version_id", "level", name="uq_exercise_hint_level"),
    )
    op.create_index("ix_exercise_hints_exercise_version_id", "exercise_hints", ["exercise_version_id"])

    op.create_table(
        "hint_reveals",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("hint_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("revealed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("level BETWEEN 1 AND 5", name="ck_hint_reveal_level"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_version_id"], ["exercise_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hint_id"], ["exercise_hints.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "exercise_version_id",
            "level",
            name="uq_hint_reveal_user_version_level",
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_hint_reveal_idempotency"),
    )
    op.create_index("ix_hint_reveals_user_id", "hint_reveals", ["user_id"])
    op.create_index("ix_hint_reveals_exercise_version_id", "hint_reveals", ["exercise_version_id"])


def downgrade():
    op.drop_index("ix_hint_reveals_exercise_version_id", table_name="hint_reveals")
    op.drop_index("ix_hint_reveals_user_id", table_name="hint_reveals")
    op.drop_table("hint_reveals")
    op.drop_index("ix_exercise_hints_exercise_version_id", table_name="exercise_hints")
    op.drop_table("exercise_hints")
    op.drop_index("ix_exercise_versions_lesson_id", table_name="exercise_versions")
    op.drop_index("ix_exercise_versions_exercise_id", table_name="exercise_versions")
    op.drop_table("exercise_versions")
