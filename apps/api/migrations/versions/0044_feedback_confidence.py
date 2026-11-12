"""AI answer feedback and pre-check confidence.

Revision ID: 0044_feedback_confidence
Revises: 0043_analytics_flags
"""
from alembic import op
import sqlalchemy as sa

revision = "0044_feedback_confidence"
down_revision = "0043_analytics_flags"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(280), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["mentor_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_ai_feedback_message"),
    )
    op.create_index("ix_ai_feedback_user_id", "ai_feedback", ["user_id"])
    op.create_index("ix_ai_feedback_message_id", "ai_feedback", ["message_id"])

    op.create_table(
        "confidence_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.String(80), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence BETWEEN 1 AND 5", name="ck_confidence_range"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_confidence_reports_user_id", "confidence_reports", ["user_id"])
    op.create_index("ix_confidence_reports_lesson_id", "confidence_reports", ["lesson_id"])


def downgrade():
    op.drop_index("ix_confidence_reports_lesson_id", table_name="confidence_reports")
    op.drop_index("ix_confidence_reports_user_id", table_name="confidence_reports")
    op.drop_table("confidence_reports")
    op.drop_index("ix_ai_feedback_message_id", table_name="ai_feedback")
    op.drop_index("ix_ai_feedback_user_id", table_name="ai_feedback")
    op.drop_table("ai_feedback")
