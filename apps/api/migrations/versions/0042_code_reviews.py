"""Rubric code reviews with a server-computed score.

Revision ID: 0042_code_reviews
Revises: 0041_tutor_modes
"""
from alembic import op
import sqlalchemy as sa

revision = "0042_code_reviews"
down_revision = "0041_tutor_modes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "code_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.String(80), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("level", sa.String(24), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("grades", sa.JSON(), nullable=False),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["coding_attempts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_reviews_user_id", "code_reviews", ["user_id"])
    op.create_index("ix_code_reviews_exercise_id", "code_reviews", ["exercise_id"])


def downgrade():
    op.drop_index("ix_code_reviews_exercise_id", table_name="code_reviews")
    op.drop_index("ix_code_reviews_user_id", table_name="code_reviews")
    op.drop_table("code_reviews")
