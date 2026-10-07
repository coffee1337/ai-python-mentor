"""Add owned, version-bound private drafts and durable clear revisions.

Revision ID: 0038_study_drafts
Revises: 0037_lesson_reflections
"""
from alembic import op
import sqlalchemy as sa

revision = "0038_study_drafts"
down_revision = "0037_lesson_reflections"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "study_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("milestone_id", sa.String(80), server_default="", nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("exercise_version_id", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["learner_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_version_id"], ["exercise_versions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "kind", "resource_id", "version", "milestone_id", name="uq_study_draft_identity"),
        sa.CheckConstraint("kind IN ('lesson_flow','coding','reflection','project_milestone')", name="ck_study_draft_kind"),
        sa.CheckConstraint("revision >= 1", name="ck_study_draft_revision"),
        sa.CheckConstraint(
            "(kind = 'project_milestone' AND version = 0 AND milestone_id <> '' AND project_id IS NOT NULL AND exercise_version_id IS NULL) OR "
            "(kind <> 'project_milestone' AND version >= 1 AND milestone_id = '' AND project_id IS NULL AND exercise_version_id IS NOT NULL)",
            name="ck_study_draft_context",
        ),
    )
    op.create_index("ix_study_drafts_user_id", "study_drafts", ["user_id"])


def downgrade():
    # The new private drafts are removed; all pre-existing account/learning data
    # and immutable authored catalogs remain untouched.
    op.drop_index("ix_study_drafts_user_id", table_name="study_drafts")
    op.drop_table("study_drafts")
