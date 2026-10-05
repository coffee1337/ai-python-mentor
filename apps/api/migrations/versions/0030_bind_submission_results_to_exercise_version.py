"""Bind coding attempts and normalized results to immutable exercise versions."""

from alembic import op
import sqlalchemy as sa


revision = "0030_bind_submission_results_to_exercise_version"
down_revision = "0029_submission_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL preserves pre-0030 history: those attempts have no trustworthy
    # version and therefore remain ineligible for dispatch/evidence.
    with op.batch_alter_table("coding_attempts") as batch_op:
        batch_op.add_column(sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_coding_attempts_exercise_version_id",
            "exercise_versions",
            ["exercise_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_coding_attempts_exercise_version_id", ["exercise_version_id"])

    with op.batch_alter_table("submission_results") as batch_op:
        batch_op.add_column(sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_submission_results_exercise_version_id",
            "exercise_versions",
            ["exercise_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_submission_results_exercise_version_id", ["exercise_version_id"])


def downgrade() -> None:
    bind = op.get_bind()
    versioned_attempts = bind.execute(
        sa.text(
            "SELECT count(*) FROM coding_attempts "
            "WHERE exercise_version_id IS NOT NULL"
        )
    ).scalar_one()
    versioned_results = bind.execute(
        sa.text(
            "SELECT count(*) FROM submission_results "
            "WHERE exercise_version_id IS NOT NULL"
        )
    ).scalar_one()
    if versioned_attempts or versioned_results:
        raise RuntimeError(
            "Refusing downgrade: version-bound runner data would be discarded"
        )

    with op.batch_alter_table("submission_results") as batch_op:
        batch_op.drop_index("ix_submission_results_exercise_version_id")
        batch_op.drop_constraint(
            "fk_submission_results_exercise_version_id",
            type_="foreignkey",
        )
        batch_op.drop_column("exercise_version_id")

    with op.batch_alter_table("coding_attempts") as batch_op:
        batch_op.drop_index("ix_coding_attempts_exercise_version_id")
        batch_op.drop_constraint(
            "fk_coding_attempts_exercise_version_id",
            type_="foreignkey",
        )
        batch_op.drop_column("exercise_version_id")
