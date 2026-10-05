"""Persist immutable deterministic curriculum revisions and sessions."""
from datetime import datetime, timezone
from uuid import uuid4
import sqlalchemy as sa
from alembic import op

revision = "0012_curriculum_engine"
down_revision = "0011_skill_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "curriculum_plan_revisions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(32), server_default="curriculum-v1", nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("goal_snapshot", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("coverage", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["learning_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "version", name="uq_curriculum_revision_version"),
    )
    op.create_index("ix_curriculum_plan_revisions_plan_id", "curriculum_plan_revisions", ["plan_id"])
    op.create_table(
        "curriculum_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("revision_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("target_minutes", sa.Integer(), nullable=False),
        sa.Column("planned_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="planned", nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["curriculum_plan_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "position", name="uq_curriculum_session_position"),
    )
    op.create_index("ix_curriculum_sessions_revision_id", "curriculum_sessions", ["revision_id"])
    op.create_table(
        "curriculum_activities",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("lesson_id", sa.String(80)),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("reason_codes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("availability", sa.String(32), server_default="available", nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["curriculum_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "position", name="uq_curriculum_activity_position"),
    )
    op.create_index("ix_curriculum_activities_session_id", "curriculum_activities", ["session_id"])

    # Preserve the currently materialized plan as a read-only legacy revision.
    bind = op.get_bind()
    plans = sa.table("learning_plans", sa.column("id"), sa.column("user_id"), sa.column("version"), sa.column("generated_at"))
    items = sa.table("learning_plan_items", sa.column("plan_id"), sa.column("lesson_id"), sa.column("skill_id"), sa.column("position"), sa.column("focus_score"))
    revisions = sa.table("curriculum_plan_revisions", sa.column("id"), sa.column("plan_id"), sa.column("version"), sa.column("policy_version"), sa.column("as_of"), sa.column("goal_snapshot"), sa.column("coverage"), sa.column("reason"))
    sessions = sa.table("curriculum_sessions", sa.column("id"), sa.column("revision_id"), sa.column("position"), sa.column("target_minutes"), sa.column("planned_minutes"), sa.column("status"), sa.column("rationale"))
    activities = sa.table("curriculum_activities", sa.column("id"), sa.column("session_id"), sa.column("position"), sa.column("kind"), sa.column("lesson_id"), sa.column("skill_id"), sa.column("estimated_minutes"), sa.column("priority"), sa.column("reason_codes"), sa.column("availability"))
    for plan in bind.execute(sa.select(plans)).mappings():
        revision_id, session_id = uuid4(), uuid4()
        bind.execute(revisions.insert().values(
            id=revision_id, plan_id=plan["id"], version=plan["version"] or 1,
            policy_version="legacy-import", as_of=plan["generated_at"] or datetime.now(timezone.utc),
            goal_snapshot={}, coverage={"source": "existing_learning_plan", "vacancy_fit": "unavailable"},
            reason="legacy_import",
        ))
        old_items = list(bind.execute(sa.select(items).where(items.c.plan_id == plan["id"]).order_by(items.c.position)).mappings())
        bind.execute(sessions.insert().values(
            id=session_id, revision_id=revision_id, position=1, target_minutes=0,
            planned_minutes=0, status="planned",
            rationale="Импортирована существующая версия плана; длительность источника не указана.",
        ))
        for item in old_items:
            bind.execute(activities.insert().values(
                id=uuid4(), session_id=session_id, position=item["position"], kind="lesson",
                lesson_id=item["lesson_id"], skill_id=item["skill_id"], estimated_minutes=0,
                priority=item["focus_score"], reason_codes=["legacy_import"], availability="legacy",
            ))


def downgrade():
    op.drop_index("ix_curriculum_activities_session_id", table_name="curriculum_activities")
    op.drop_table("curriculum_activities")
    op.drop_index("ix_curriculum_sessions_revision_id", table_name="curriculum_sessions")
    op.drop_table("curriculum_sessions")
    op.drop_index("ix_curriculum_plan_revisions_plan_id", table_name="curriculum_plan_revisions")
    op.drop_table("curriculum_plan_revisions")
