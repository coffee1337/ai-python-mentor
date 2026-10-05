"""Durable, owned coding jobs; does not execute or backfill legacy attempts."""
from alembic import op
import sqlalchemy as sa

revision = "0035_execution_jobs"
down_revision = "0034_product_features"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("execution_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coding_attempt_id", sa.Uuid(), sa.ForeignKey("coding_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_key_digest", sa.String(64), nullable=False),
        sa.Column("body_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "request_key_digest", name="uq_execution_jobs_user_request_key"),
        sa.UniqueConstraint("coding_attempt_id"),
        sa.CheckConstraint("status IN ('queued','running','finished','failed','cancelled','unavailable')", name="ck_execution_jobs_status"),
    )
    op.create_index("ix_execution_jobs_user_id", "execution_jobs", ["user_id"])
    op.create_index("ix_execution_jobs_status_created", "execution_jobs", ["status", "created_at"])

def downgrade():
    # Existing attempts/results/evidence survive; only queue metadata is removed.
    connection = op.get_bind()
    active = connection.execute(sa.text("SELECT count(*) FROM execution_jobs WHERE status IN ('queued','running')")).scalar_one()
    if active:
        raise RuntimeError("Stop admission and drain execution jobs before downgrade")
    op.drop_index("ix_execution_jobs_status_created", table_name="execution_jobs")
    op.drop_index("ix_execution_jobs_user_id", table_name="execution_jobs")
    op.drop_table("execution_jobs")
