"""Telegram channel: binding lifecycle columns and webhook dedupe ledger.

Revision ID: 0040_telegram_bot
Revises: 0039_study_sessions
"""
from alembic import op
import sqlalchemy as sa

revision = "0040_telegram_bot"
down_revision = "0039_study_sessions"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("telegram_bindings") as batch:
        batch.alter_column("chat_id", existing_type=sa.String(32), type_=sa.String(40), existing_nullable=False)
        batch.add_column(sa.Column("username", sa.String(64), nullable=True))
        batch.add_column(sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("quiet_hours", sa.String(11), nullable=True))
        batch.add_column(sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "telegram_updates",
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.String(40), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("update_id"),
    )


def downgrade():
    op.drop_table("telegram_updates")
    with op.batch_alter_table("telegram_bindings") as batch:
        batch.drop_column("revoked_at")
        batch.drop_column("quiet_hours")
        batch.drop_column("notifications_enabled")
        batch.drop_column("username")
        batch.alter_column("chat_id", existing_type=sa.String(40), type_=sa.String(32), existing_nullable=False)
