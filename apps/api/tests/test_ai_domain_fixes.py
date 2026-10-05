from datetime import datetime, timezone

from sqlalchemy import select

from app.ai_curriculum import _snapshot
from app.curriculum import build_curriculum
from app.db.models import CurriculumActivity, CurriculumSession, Goal, LearningPlan, User, UserSkill
from app.db.session import get_db
from app.main import app
from test_auth import client
from test_learning import register, onboard


def test_ai_allowlist_requires_transitive_prerequisites(client):
    register(client)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        # A strong immediate prerequisite cannot hide missing ancestors.
        db.add(UserSkill(user_id=user.id, skill_id="python.loops", knowledge_score=1,
                         independent_score=1, practice_score=1, evidence_count=1))
        db.flush()
        snapshot, _, _ = _snapshot(db, user)
        assert "python.functions" not in {item["skill_id"] for item in snapshot["skills"]}


def test_curriculum_durations_sum_to_planned_time_and_fit_real_budget(client):
    register(client)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        goal = db.scalar(select(Goal).where(Goal.user_id == user.id))
        goal.weekly_minutes = 15
        db.add(LearningPlan(user_id=user.id, recommendation_text="initial"))
        db.flush()
        revision = build_curriculum(db, user)
        db.flush()
        session = db.scalar(select(CurriculumSession).where(CurriculumSession.revision_id == revision.id))
        activities = list(db.scalars(select(CurriculumActivity).where(CurriculumActivity.session_id == session.id)))
        assert activities
        assert session.planned_minutes == sum(item.estimated_minutes for item in activities)
        assert 0 < session.planned_minutes <= session.target_minutes == 15
