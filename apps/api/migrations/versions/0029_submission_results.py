"""Persist normalized Runner results and visibility-scoped test outcomes."""

from alembic import op
import sqlalchemy as sa


revision = "0029_submission_results"
down_revision = "0028_correct_variables_data_types_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing CodingAttempt history is intentionally not backfilled: old
    # rows have no trustworthy idempotency key or per-test Runner result.
    op.create_table(
        "submission_results",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("coding_attempt_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_evidence_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(240), nullable=False),
        sa.Column("protocol_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("tests_passed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tests_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("timeout", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("resource_violation", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["coding_attempt_id"],
            ["coding_attempts.id"],
            name="fk_submission_results_coding_attempt_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_evidence_id"],
            ["skill_evidence.id"],
            name="fk_submission_results_skill_evidence_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submission_results"),
        sa.UniqueConstraint(
            "coding_attempt_id",
            name="uq_submission_results_coding_attempt",
        ),
        sa.UniqueConstraint(
            "skill_evidence_id",
            name="uq_submission_results_skill_evidence",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_submission_results_idempotency_key",
        ),
        sa.CheckConstraint(
            "status IN ('finished', 'passed', 'failed', 'timeout', "
            "'resource_violation', 'error', 'runner_error', 'unavailable')",
            name="ck_submission_results_status",
        ),
        sa.CheckConstraint(
            "tests_passed >= 0 AND tests_total >= 0 AND tests_passed <= tests_total",
            name="ck_submission_results_test_counts",
        ),
        sa.CheckConstraint(
            "protocol_version >= 1",
            name="ck_submission_results_protocol_version",
        ),
    )

    op.create_table(
        "submission_test_results",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("submission_result_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("test_index", sa.Integer(), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_result_id"],
            ["submission_results.id"],
            name="fk_submission_test_results_submission_result_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submission_test_results"),
        sa.UniqueConstraint(
            "submission_result_id",
            "test_index",
            name="uq_submission_test_results_result_index",
        ),
        sa.CheckConstraint(
            "test_index >= 0",
            name="ck_submission_test_results_index",
        ),
        sa.CheckConstraint(
            "visibility IN ('public', 'hidden')",
            name="ck_submission_test_results_visibility",
        ),
        sa.CheckConstraint(
            "status IN ('passed', 'failed', 'error', 'not_run')",
            name="ck_submission_test_results_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("submission_test_results")
    op.drop_table("submission_results")
