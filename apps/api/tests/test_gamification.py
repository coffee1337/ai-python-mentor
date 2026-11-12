"""Streak, XP and achievements are derived from verified actions, not awarded.

The tests fix the pricing rules and the streak edges: a missed day breaks the run,
a completion today or yesterday keeps it alive, and nothing depends on a model.
"""
from datetime import UTC, datetime, timedelta

import pytest
from test_auth import client, csrf

from app.db.models import CodingAttempt, KnowledgeCheckAttempt, LessonCompletion, User
from app.db.session import get_db
from app.gamification import XP_CODING_PASS, XP_KNOWLEDGE_CHECK, XP_LESSON, current_streak, level_for, longest_streak
from app.main import app


def seed(user_id, *, lessons=0, checks=0, passes=0, days=(0,)):
    with next(app.dependency_overrides[get_db]()) as db:
        now = datetime.now(UTC)
        for index in range(lessons):
            db.add(LessonCompletion(user_id=user_id, lesson_id=f"lesson-{index + lessons}",
                                    answer="knowledge_check", completed_at=now - timedelta(days=days[index % len(days)])))
        for _ in range(checks):
            db.add(KnowledgeCheckAttempt(user_id=user_id, exercise_version_id=None, lesson_id="l",
                                         skill_id="python.variables", score=1.0, passed=True, created_at=now))
        for _ in range(passes):
            db.add(CodingAttempt(user_id=user_id, exercise_id="variables-v1-code", exercise_version_id=None,
                                 language="python", mode="function", source_code="def solve(p): return p",
                                 status="passed", result="{}"))
        db.commit()


def me(db):
    return db.scalar(__import__("sqlalchemy").select(User))


def test_streak_counts_days_with_a_completion():
    today = datetime(2026, 11, 12, tzinfo=UTC).date()
    days = [today, today - timedelta(days=1), today - timedelta(days=2)]
    assert current_streak(days, today=datetime(2026, 11, 12, tzinfo=UTC)) == 3
    # A gap breaks the run at the gap, not at the start.
    gapped = [today, today - timedelta(days=2), today - timedelta(days=3)]
    assert current_streak(gapped, today=datetime(2026, 11, 12, tzinfo=UTC)) == 1
    # Yesterday still counts (the day is not over).
    assert current_streak([today - timedelta(days=1)], today=datetime(2026, 11, 12, tzinfo=UTC)) == 1
    # Older than yesterday does not.
    assert current_streak([today - timedelta(days=3)], today=datetime(2026, 11, 12, tzinfo=UTC)) == 0
    assert current_streak([], today=datetime(2026, 11, 12, tzinfo=UTC)) == 0


def test_longest_streak_is_computed_over_all_days():
    start = datetime(2026, 1, 1, tzinfo=UTC).date()
    days = [start, start + timedelta(days=1), start + timedelta(days=3), start + timedelta(days=4), start + timedelta(days=5)]
    assert longest_streak(days) == 3


def test_levels_are_a_fixed_table():
    assert level_for(0)[:2] == (0, "Новичок")
    assert level_for(99)[0] == 0
    assert level_for(100)[0] == 1
    assert level_for(1000)[0] == 5
    assert level_for(1000)[2] is None, "верхний уровень не обещает следующий"


def test_api_returns_the_same_numbers_as_the_pricing_table(client):
    from sqlalchemy import select

    client.post("/auth/register", json={"email": "xp@example.com", "password": "Correct-Horse-Battery-9"})
    client.post("/onboarding", json={"experience_level": "beginner", "target_role": "Python backend", "weekly_minutes": 180},
                headers={"X-CSRF-Token": csrf(client)})
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        user_id = user.id
    seed(user_id, lessons=3, checks=2, passes=1)

    response = client.get("/me/progress")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["xp"] == 3 * XP_LESSON + 2 * XP_KNOWLEDGE_CHECK + 1 * XP_CODING_PASS
    assert body["level"] == level_for(body["xp"])[0]
    assert body["lessons"] == 3 and body["knowledge_checks"] == 2 and body["coding_passes"] == 1
    assert body["streak_days"] >= 1


def test_achievements_are_predicates_over_facts(client):
    from sqlalchemy import select

    client.post("/auth/register", json={"email": "ach@example.com", "password": "Correct-Horse-Battery-9"})
    client.post("/onboarding", json={"experience_level": "beginner", "target_role": "Python backend", "weekly_minutes": 180},
                headers={"X-CSRF-Token": csrf(client)})
    with next(app.dependency_overrides[get_db]()) as db:
        user_id = db.scalar(select(User.id))
    fresh = client.get("/me/progress").json()
    assert {item["id"]: item["earned"] for item in fresh["achievements"]}["first_step"] is False

    seed(user_id, lessons=1, passes=1)
    after = client.get("/me/progress").json()
    earned = {item["id"]: item["earned"] for item in after["achievements"]}
    assert earned["first_step"] is True and earned["code_runs"] is True
    assert earned["week_streak"] is False, "неделя не награждается за один день"


def test_progress_requires_an_account(client):
    assert client.get("/me/progress").status_code == 401
