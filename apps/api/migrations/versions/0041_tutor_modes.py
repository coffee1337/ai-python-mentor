"""Tutor mode chosen for each mentor message.

Revision ID: 0041_tutor_modes
Revises: 0040_telegram_bot
"""
from alembic import op
import sqlalchemy as sa

revision = "0041_tutor_modes"
down_revision = "0040_telegram_bot"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("mentor_messages") as batch:
        batch.add_column(sa.Column("mode", sa.String(24), nullable=True))


def downgrade():
    with op.batch_alter_table("mentor_messages") as batch:
        batch.drop_column("mode")
