"""Add the missing ai_usage_ledger user index declared on the model.

0013 created the table but omitted ix_ai_usage_ledger_user_id, so `alembic check`
reported a pending add_index while every query filtered by user_id.
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_ai_usage_ledger_user_index"
down_revision = "0013_ai_curriculum"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_ai_usage_ledger_user_id"
TABLE_NAME = "ai_usage_ledger"


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if INDEX_NAME in {index["name"] for index in inspector.get_indexes(TABLE_NAME)}:
        return
    op.create_index(INDEX_NAME, TABLE_NAME, ["user_id"])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if INDEX_NAME in {index["name"] for index in inspector.get_indexes(TABLE_NAME)}:
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
