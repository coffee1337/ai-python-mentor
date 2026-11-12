"""Product events and feature-flag overrides.

Revision ID: 0043_analytics_flags
Revises: 0042_code_reviews
"""
from alembic import op
import sqlalchemy as sa

revision = "0043_analytics_flags"
down_revision = "0042_code_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("props", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_events_user_id", "product_events", ["user_id"])
    op.create_index("ix_product_events_name", "product_events", ["name"])
    op.create_index("ix_product_events_created_at", "product_events", ["created_at"])

    op.create_table(
        "feature_flag_overrides",
        sa.Column("flag", sa.String(48), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("flag", "user_id"),
    )


def downgrade():
    op.drop_table("feature_flag_overrides")
    op.drop_index("ix_product_events_created_at", table_name="product_events")
    op.drop_index("ix_product_events_name", table_name="product_events")
    op.drop_index("ix_product_events_user_id", table_name="product_events")
    op.drop_table("product_events")
