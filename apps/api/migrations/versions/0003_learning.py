"""Add per-user authored lesson completion evidence."""
import sqlalchemy as sa
from alembic import op

revision = "0003_learning"
down_revision = "0002_auth_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lesson_completions",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("lesson_id", sa.String(80), nullable=False),
        sa.Column("answer", sa.String(200), nullable=False),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "lesson_id"),
    )


def downgrade() -> None:
    op.drop_table("lesson_completions")
