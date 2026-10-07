"""Add owned study timers without changing learning evidence or recommendations.

Revision ID: 0039_study_sessions
Revises: 0038_study_drafts
"""
from alembic import op
import sqlalchemy as sa

revision = "0039_study_sessions"
down_revision = "0038_study_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("study_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("last_activity_at", sa.DateTime(timezone=True)),
        sa.Column("accumulated_milliseconds", sa.Integer(), nullable=False),
        sa.Column("focus_snapshot", sa.JSON(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("target_minutes", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('active', 'paused', 'completed', 'abandoned')", name="ck_study_session_status"),
        sa.CheckConstraint("revision >= 1", name="ck_study_session_revision"),
        sa.CheckConstraint("accumulated_milliseconds BETWEEN 0 AND 28800000", name="ck_study_session_duration"),
        sa.CheckConstraint("estimated_minutes >= 0 AND target_minutes BETWEEN 0 AND 60", name="ck_study_session_estimate"),
        sa.CheckConstraint("(status IN ('completed', 'abandoned') AND ended_at IS NOT NULL AND last_activity_at IS NULL) OR "
                           "(status IN ('active', 'paused') AND ended_at IS NULL)", name="ck_study_session_end"),
        sa.CheckConstraint("(status = 'active' AND last_activity_at IS NOT NULL) OR "
                           "(status != 'active' AND last_activity_at IS NULL)", name="ck_study_session_segment"),
    )
    op.create_index("ix_study_sessions_owner_started", "study_sessions", ["user_id", "started_at"])
    op.create_index("uq_study_session_open_owner", "study_sessions", ["user_id"], unique=True,
                    sqlite_where=sa.text("status IN ('active', 'paused')"),
                    postgresql_where=sa.text("status IN ('active', 'paused')"))


def downgrade():
    # Only this feature's timer history is removed; account, drafts, content,
    # recommendation and learning evidence tables are left intact.
    op.drop_index("uq_study_session_open_owner", table_name="study_sessions")
    op.drop_index("ix_study_sessions_owner_started", table_name="study_sessions")
    op.drop_table("study_sessions")
