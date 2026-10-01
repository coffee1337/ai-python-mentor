"""Add owned lesson mentor conversations and messages."""
import sqlalchemy as sa
from alembic import op

revision = "0004_mentor_chat"
down_revision = "0003_learning"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "mentor_conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("lesson_id", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "lesson_id", name="uq_mentor_user_lesson"),
    )
    op.create_index("ix_mentor_conversations_user_id", "mentor_conversations", ["user_id"])
    op.create_table(
        "mentor_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
        sa.Column("reply_to_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["mentor_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reply_to_id"], ["mentor_messages.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("reply_to_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mentor_messages_conversation_id", "mentor_messages", ["conversation_id"])

def downgrade() -> None:
    op.drop_table("mentor_messages")
    op.drop_index("ix_mentor_conversations_user_id", table_name="mentor_conversations")
    op.drop_table("mentor_conversations")
