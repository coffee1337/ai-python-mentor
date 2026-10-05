"""Durable AI quotas and fenced request leases without storing prompt data."""
import sqlalchemy as sa
from alembic import op

revision = "0032_domain_admission"
down_revision = "0031_knowledge_chunks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_generation_inputs",
        sa.Column("generation_id", sa.Uuid(as_uuid=True), sa.ForeignKey("ai_plan_generations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("input_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_ai_generation_inputs_input_hash", "ai_generation_inputs", ["input_hash"])
    op.create_table(
        "ai_request_leases",
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("operation", sa.String(40), primary_key=True),
        sa.Column("request_key", sa.String(160), primary_key=True),
        sa.Column("lease_token", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('processing', 'completed', 'failed')", name="ck_ai_request_lease_status"),
    )
    op.create_table(
        "ai_call_reservations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("request_key", sa.String(160), nullable=False),
        sa.Column("lease_token", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("input_chars", sa.Integer, nullable=False),
        sa.Column("reserved_micro_usd", sa.Integer, nullable=False, server_default="0"),
        sa.Column("charged_micro_usd", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_is_estimate", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("status", sa.String(20), nullable=False, server_default="reserved"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("reserved_micro_usd >= 0 AND charged_micro_usd >= 0", name="ck_ai_reservation_cost"),
        sa.CheckConstraint("input_chars >= 0", name="ck_ai_reservation_input_size"),
    )
    op.create_index("ix_ai_reservations_user_operation_time", "ai_call_reservations", ["user_id", "operation", "created_at"])


def downgrade():
    op.drop_index("ix_ai_reservations_user_operation_time", table_name="ai_call_reservations")
    op.drop_table("ai_call_reservations")
    op.drop_table("ai_request_leases")
    op.drop_index("ix_ai_generation_inputs_input_hash", table_name="ai_generation_inputs")
    op.drop_table("ai_generation_inputs")
