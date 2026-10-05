"""Persist immutable version bound written practice.

Revision ID: 0037_lesson_reflections
Revises: 0036_content_completion
"""
from alembic import op
import sqlalchemy as sa

revision = "0037_lesson_reflections"
down_revision = "0036_content_completion"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("lesson_reflections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_version_id"], ["exercise_versions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_reflection_user_key"),
    )
    op.create_index("ix_lesson_reflections_user_id", "lesson_reflections", ["user_id"])


def downgrade():
    op.drop_index("ix_lesson_reflections_user_id", table_name="lesson_reflections")
    op.drop_table("lesson_reflections")
