"""Persist validated AI curriculum generations and usage."""
import sqlalchemy as sa
from alembic import op

revision = "0013_ai_curriculum"
down_revision = "0012_curriculum_engine"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_plan_generations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_revision_id", sa.Uuid(as_uuid=True)),
        sa.Column("model_id", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), server_default="ready", nullable=False),
        sa.Column("trigger", sa.String(40), nullable=False),
        sa.Column("total_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["curriculum_plan_revisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "input_hash", "model_id", name="uq_ai_plan_cache_key"),
    )
    op.create_index("ix_ai_plan_generations_user_id", "ai_plan_generations", ["user_id"])
    op.create_table(
        "ai_plan_current",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("generation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generation_id"], ["ai_plan_generations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("generation_id"),
    )
    op.create_table(
        "ai_plan_steps",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("generation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("example_code", sa.Text(), nullable=False),
        sa.Column("exercise_prompt", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("submission_type", sa.String(20), nullable=False),
        sa.Column("starter_code", sa.Text()),
        sa.Column("constraints", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("success_criteria", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("evaluation_criteria", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("reason_codes", sa.JSON(), server_default="[]", nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["ai_plan_generations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generation_id", "position", name="uq_ai_plan_step_position"),
    )
    op.create_index("ix_ai_plan_steps_generation_id", "ai_plan_steps", ["generation_id"])
    op.create_table(
        "ai_usage_ledger",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("generation_id", sa.Uuid(as_uuid=True)),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("model_id", sa.String(120), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("input_chars", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_chars", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generation_id"], ["ai_plan_generations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("ai_usage_ledger")
    op.drop_table("ai_plan_current")
    op.drop_index("ix_ai_plan_steps_generation_id", table_name="ai_plan_steps")
    op.drop_table("ai_plan_steps")
    op.drop_index("ix_ai_plan_generations_user_id", table_name="ai_plan_generations")
    op.drop_table("ai_plan_generations")
