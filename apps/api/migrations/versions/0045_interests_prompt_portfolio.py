"""Learner interests, prompt versioning, AI latency and the portfolio explanation.

Revision ID: 0045_interests_prompt_portfolio
Revises: 0044_feedback_confidence
"""
from alembic import op
import sqlalchemy as sa

revision = "0045_interests_prompt_portfolio"
down_revision = "0044_feedback_confidence"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("profiles") as batch:
        batch.add_column(sa.Column("interests", sa.JSON(), nullable=True))
    with op.batch_alter_table("portfolio_entries") as batch:
        batch.add_column(sa.Column("explanation", sa.String(2000), nullable=True))
    with op.batch_alter_table("ai_usage_ledger") as batch:
        batch.add_column(sa.Column("prompt_version", sa.String(40), nullable=True))
        batch.add_column(sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.create_table(
        "ai_eval_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("cases", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("ai_eval_runs")
    with op.batch_alter_table("ai_usage_ledger") as batch:
        batch.drop_column("latency_ms")
        batch.drop_column("prompt_version")
    with op.batch_alter_table("portfolio_entries") as batch:
        batch.drop_column("explanation")
    with op.batch_alter_table("profiles") as batch:
        batch.drop_column("interests")
