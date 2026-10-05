"""Persist owned coding attempts and normalized runner results."""
import sqlalchemy as sa
from alembic import op

revision = "0005_coding_attempts"
down_revision = "0004_mentor_chat"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "coding_attempts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("exercise_id", sa.String(80), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coding_attempts_user_id", "coding_attempts", ["user_id"])
    op.create_index("ix_coding_attempts_exercise_id", "coding_attempts", ["exercise_id"])

def downgrade() -> None:
    op.drop_index("ix_coding_attempts_exercise_id", table_name="coding_attempts")
    op.drop_index("ix_coding_attempts_user_id", table_name="coding_attempts")
    op.drop_table("coding_attempts")
