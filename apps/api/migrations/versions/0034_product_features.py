"""Owned vacancies, project artifacts, portfolio and generated attempt provenance.

Additive only. Downgrade removes these new feature records, preserving all
pre-existing users, authored content, attempts and mastery evidence.
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_product_features"
down_revision = "0033_account_services"
branch_labels = None
depends_on = None


def _uuid(name, target=None, primary=False, nullable=False):
    args = [sa.ForeignKey(target, ondelete="RESTRICT" if target == "exercise_versions.id" else "CASCADE")] if target else []
    return sa.Column(name, sa.Uuid(as_uuid=True), *args, primary_key=primary, nullable=nullable)


def _created(name="created_at"):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade():
    op.create_table("vacancy_analyses", _uuid("id", primary=True), _uuid("user_id", "users.id"),
                    sa.Column("title", sa.String(160), nullable=False), sa.Column("source_text", sa.Text, nullable=False),
                    sa.Column("source_url", sa.String(2048), nullable=True), sa.Column("analyzer_version", sa.String(40), nullable=False),
                    sa.Column("requirements", sa.JSON, nullable=False), _created())
    op.create_index("ix_vacancy_analyses_user_id", "vacancy_analyses", ["user_id"])
    op.create_table("vacancy_targets", _uuid("user_id", "users.id", primary=True),
                    _uuid("vacancy_id", "vacancy_analyses.id"), _created("selected_at"))
    op.create_table("learner_projects", _uuid("id", primary=True), _uuid("user_id", "users.id"),
                    sa.Column("template_id", sa.String(80), nullable=False), sa.Column("template_snapshot", sa.JSON, nullable=False),
                    _created(), sa.UniqueConstraint("user_id", "template_id", name="uq_project_owner_template"))
    op.create_index("ix_learner_projects_user_id", "learner_projects", ["user_id"])
    op.create_table("project_submissions", _uuid("id", primary=True), _uuid("project_id", "learner_projects.id"),
                    sa.Column("milestone_id", sa.String(80), nullable=False), sa.Column("idempotency_key", sa.String(100), nullable=False),
                    sa.Column("payload_hash", sa.String(64), nullable=False), sa.Column("artifact_text", sa.Text, nullable=False),
                    sa.Column("repository_url", sa.String(2048), nullable=True), sa.Column("validation", sa.JSON, nullable=False),
                    _created(), sa.UniqueConstraint("project_id", "idempotency_key", name="uq_project_submission_idempotency"))
    op.create_index("ix_project_submissions_project_id", "project_submissions", ["project_id"])
    op.create_table("portfolio_entries", _uuid("id", primary=True), _uuid("user_id", "users.id"),
                    _uuid("project_id", "learner_projects.id"), sa.Column("public_token", sa.String(64), nullable=False),
                    sa.Column("published", sa.Boolean, nullable=False, server_default="false"),
                    sa.Column("title", sa.String(160), nullable=False), sa.Column("summary", sa.String(2000), nullable=False),
                    sa.Column("repository_url", sa.String(2048), nullable=True), _created("updated_at"),
                    sa.UniqueConstraint("project_id"), sa.UniqueConstraint("public_token"))
    op.create_index("ix_portfolio_entries_user_id", "portfolio_entries", ["user_id"])
    op.create_table("generated_practice_bindings", _uuid("step_id", "ai_plan_steps.id", primary=True),
                    sa.Column("exercise_id", sa.String(80), nullable=False), _uuid("exercise_version_id", "exercise_versions.id"))
    op.create_table("generated_exercise_attempts", _uuid("id", primary=True), _uuid("user_id", "users.id"),
                    _uuid("generation_id", "ai_plan_generations.id"), _uuid("step_id", "ai_plan_steps.id"),
                    _uuid("coding_attempt_id", "coding_attempts.id", nullable=True),
                    sa.Column("idempotency_key", sa.String(100), nullable=False), sa.Column("payload_hash", sa.String(64), nullable=False),
                    sa.Column("answer", sa.Text, nullable=False), sa.Column("exercise_snapshot", sa.JSON, nullable=False),
                    sa.Column("status", sa.String(24), nullable=False), sa.Column("feedback", sa.JSON, nullable=False), _created(),
                    sa.UniqueConstraint("coding_attempt_id"),
                    sa.UniqueConstraint("user_id", "idempotency_key", name="uq_generated_attempt_idempotency"),
                    sa.CheckConstraint("status IN ('pending', 'reviewed', 'unavailable', 'coding_result')", name="ck_generated_attempt_status"))
    op.create_index("ix_generated_exercise_attempts_user_id", "generated_exercise_attempts", ["user_id"])
    op.create_index("ix_generated_exercise_attempts_generation_id", "generated_exercise_attempts", ["generation_id"])


def downgrade():
    op.drop_index("ix_generated_exercise_attempts_generation_id", table_name="generated_exercise_attempts")
    op.drop_index("ix_generated_exercise_attempts_user_id", table_name="generated_exercise_attempts")
    op.drop_table("generated_exercise_attempts")
    op.drop_table("generated_practice_bindings")
    op.drop_index("ix_portfolio_entries_user_id", table_name="portfolio_entries")
    op.drop_table("portfolio_entries")
    op.drop_index("ix_project_submissions_project_id", table_name="project_submissions")
    op.drop_table("project_submissions")
    op.drop_index("ix_learner_projects_user_id", table_name="learner_projects")
    op.drop_table("learner_projects")
    op.drop_table("vacancy_targets")
    op.drop_index("ix_vacancy_analyses_user_id", table_name="vacancy_analyses")
    op.drop_table("vacancy_analyses")
