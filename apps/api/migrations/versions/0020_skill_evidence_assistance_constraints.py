"""Constrain SkillEvidence assistance fields to their domain invariant."""

from alembic import op


revision = "0020_skill_evidence_assistance_constraints"
down_revision = "0019_restrict_exercise_version_deletion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("skill_evidence") as batch_op:
        batch_op.drop_constraint(
            "ck_skill_evidence_hint_count",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_skill_evidence_hint_count",
            "hint_count BETWEEN 0 AND 5",
        )
        batch_op.create_check_constraint(
            "ck_skill_evidence_assistance_consistency",
            "(assisted = false AND hint_count = 0) OR "
            "(assisted = true AND hint_count > 0)",
        )


def downgrade() -> None:
    with op.batch_alter_table("skill_evidence") as batch_op:
        batch_op.drop_constraint(
            "ck_skill_evidence_assistance_consistency",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_skill_evidence_hint_count",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_skill_evidence_hint_count",
            "hint_count >= 0",
        )
