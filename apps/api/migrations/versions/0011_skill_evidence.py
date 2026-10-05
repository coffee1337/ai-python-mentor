"""Add append-only skill evidence and mastery audit."""
import sqlalchemy as sa
from alembic import op

revision = "0011_skill_evidence"
down_revision = "0010_skill_graph"
branch_labels = None
depends_on = None


def upgrade():
    # Add nullable first for populated SQLite/PostgreSQL tables, then backfill.
    op.add_column("user_skills", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE user_skills SET updated_at = last_practiced_at")
    op.execute("UPDATE user_skills SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
    with op.batch_alter_table("user_skills") as batch:
        batch.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    op.add_column("user_skills", sa.Column("mastery_weight", sa.Float(), server_default="0", nullable=False))
    # Existing aggregate rows predate the weighted-average projection.
    op.execute("UPDATE user_skills SET mastery_weight = evidence_count")
    op.create_table(
        "skill_evidence",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.Column("result_score", sa.Float(), nullable=False),
        sa.Column("assisted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("hint_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_skill_evidence_idempotency"),
        sa.CheckConstraint("source_type IN ('assessment_response', 'knowledge_check_attempt', 'coding_attempt')", name="ck_skill_evidence_source_type"),
        sa.CheckConstraint("result_score >= 0 AND result_score <= 1", name="ck_skill_evidence_result_score"),
        sa.CheckConstraint("hint_count >= 0", name="ck_skill_evidence_hint_count"),
    )
    op.create_index("ix_skill_evidence_user_id", "skill_evidence", ["user_id"])
    op.create_index("ix_skill_evidence_skill_id", "skill_evidence", ["skill_id"])
    op.create_table(
        "skill_mastery_audit",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("evidence_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("before_mastery", sa.Float(), nullable=False),
        sa.Column("after_mastery", sa.Float(), nullable=False),
        sa.Column("before_evidence_count", sa.Integer(), nullable=False),
        sa.Column("after_evidence_count", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(32), server_default="v1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["skill_evidence.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evidence_id"),
    )
    op.create_index("ix_skill_mastery_audit_user_id", "skill_mastery_audit", ["user_id"])
    op.create_index("ix_skill_mastery_audit_skill_id", "skill_mastery_audit", ["skill_id"])


def downgrade():
    op.drop_index("ix_skill_mastery_audit_skill_id", table_name="skill_mastery_audit")
    op.drop_index("ix_skill_mastery_audit_user_id", table_name="skill_mastery_audit")
    op.drop_table("skill_mastery_audit")
    op.drop_index("ix_skill_evidence_skill_id", table_name="skill_evidence")
    op.drop_index("ix_skill_evidence_user_id", table_name="skill_evidence")
    op.drop_table("skill_evidence")
    op.drop_column("user_skills", "mastery_weight")
    op.drop_column("user_skills", "updated_at")
