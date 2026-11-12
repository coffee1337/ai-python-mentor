"""Stage timestamps for execution jobs.

Revision ID: 0046_job_stages
Revises: 0045_interests_prompt_portfolio
"""
from alembic import op
import sqlalchemy as sa

revision = "0046_job_stages"
down_revision = "0045_interests_prompt_portfolio"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("execution_jobs") as batch:
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("execution_jobs") as batch:
        batch.drop_column("graded_at")
        batch.drop_column("started_at")
