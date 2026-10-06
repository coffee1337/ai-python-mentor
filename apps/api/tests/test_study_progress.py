"""Owned read projections report facts without awarding credit."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from app import study_progress
from app.db.base import Base
from app.db.models import (
    AssessmentResponse, AssessmentRun, CodingAttempt, CurriculumActivity,
    CurriculumPlanRevision, CurriculumSession, KnowledgeCheckAttempt,
    LearningPlan, LessonCompletion, LessonSession, ReviewAttempt,
    ReviewSession, SkillEvidence, User, UserSkill,
)
from app.db.session import get_db
from app.exercise_hints import _seed_exercise
from app.learning import learning_path
from app.learning_content import LESSONS, LESSONS_BY_ID
from app.main import app
from app.prerequisites import prerequisite_state
from app.skill_graph import SKILLS, seed_skill_graph
from test_auth import client, csrf

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(study_progress, "_utc_now", lambda: NOW)


def setup_user(c):
    assert c.post("/auth/register", json={"email": "study@example.com", "password": "safe-password"}).status_code == 201
    assert c.post("/onboarding", headers={"X-CSRF-Token": csrf(c)}, json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180,
    }).status_code == 200


def database():
    return next(app.dependency_overrides[get_db]())


def seeded(db):
    owner = db.scalar(select(User).where(User.email == "study@example.com"))
    seed_skill_graph(db)
    version = _seed_exercise(db, "variables-v2", seed_hints=False)
    db.flush()
    return owner, version


def add_evidence(db, owner, source_type, source_id, stamp, *, assisted=False, retention=False, score=1.0):
    row = SkillEvidence(user_id=owner.id, skill_id="python.variables", source_type=source_type,
        source_id=str(source_id), occurred_at=stamp, created_at=stamp, result_score=score,
        assisted=assisted, hint_count=2 if assisted else 0, retention_only=retention,
        idempotency_key=str(uuid4()), evidence_metadata={"answer": "SECRET-ANSWER", "key": "SECRET-KEY"})
    db.add(row)
    db.flush()
    return row


def add_check(db, owner, version, stamp, *, passed=True, assisted=False):
    row = KnowledgeCheckAttempt(user_id=owner.id, exercise_version_id=version.id, lesson_id=version.lesson_id,
        skill_id="python.variables", score=float(passed), passed=passed, created_at=stamp)
    db.add(row)
    db.flush()
    add_evidence(db, owner, "knowledge_check_attempt", row.id, stamp, assisted=assisted, score=float(passed))
    return row


def counts(db):
    return {table.name: db.scalar(select(func.count()).select_from(table)) for table in Base.metadata.sorted_tables}


def test_auth_onboarding_and_query_validation(client):
    for path in ("/learning/progress", "/learning/today"):
        assert client.get(path).status_code == 401
    client.post("/auth/register", json={"email": "study@example.com", "password": "safe-password"})
    for path in ("/learning/progress", "/learning/today"):
        assert client.get(path).status_code == 409
    client.post("/onboarding", headers={"X-CSRF-Token": csrf(client)}, json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180})
    for query in ("days=8", "days=0", "utc_offset_minutes=841", "utc_offset_minutes=-841"):
        assert client.get(f"/learning/progress?{query}").status_code == 422
    assert client.get("/learning/progress?days=30&utc_offset_minutes=-840").status_code == 200


def test_beginner_reads_do_not_publish_or_create_learning_rows(client):
    setup_user(client)
    with database() as db:
        before = counts(db)
    response = client.get("/learning/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["totals"] == {"completed_lessons": 0, "total_lessons": len(LESSONS), "observed_skills": 0, "due_reviews": 0}
    assert all(value == 0 for value in body["period"].values())
    assert len(body["days"]) == 7 and len(body["skills"]) == len(SKILLS)
    assert all(item["knowledge_score"] is None and item["retention_score"] is None for item in body["skills"])
    assert body["recent_activity"] == []
    today = client.get("/learning/today").json()
    assert today["source"] == "starter"
    assert today["next_lesson"]["id"] == "variables-v2" and today["next_lesson"]["is_resume"] is False
    assert today["focus"][0]["kind"] == "lesson"
    assert today["estimated_minutes"] == today["next_lesson"]["minutes"]
    with database() as db:
        assert counts(db) == before


def test_real_sources_and_evidence_have_separate_counts_and_no_private_data(client):
    setup_user(client)
    stamp = NOW - timedelta(hours=1)
    with database() as db:
        owner, version = seeded(db)
        add_check(db, owner, version, stamp)
        add_check(db, owner, version, stamp + timedelta(minutes=1), passed=False, assisted=True)
        db.add(LessonCompletion(user_id=owner.id, lesson_id="variables-v2", exercise_version_id=version.id,
                               answer="SECRET-ANSWER", completed_at=stamp))
        db.add(CodingAttempt(user_id=owner.id, exercise_id="variables-v2-code", language="python", mode="function",
            source_code="SECRET-SOURCE-CODE", result='{"secret":"SECRET-RUNNER"}', status="unavailable", created_at=stamp))
        review_id = uuid4()
        retention = add_evidence(db, owner, "review_attempt", review_id, stamp, retention=True)
        session = ReviewSession(user_id=owner.id, skill_id="python.variables", exercise_version_id=version.id,
                                scheduled_for=(NOW - timedelta(days=1)).date(), completed_at=stamp)
        db.add(session)
        db.flush()
        db.add(ReviewAttempt(id=review_id, user_id=owner.id, review_session_id=session.id, skill_id="python.variables",
            exercise_version_id=version.id, skill_evidence_id=retention.id, scheduled_for=session.scheduled_for,
            idempotency_key="SECRET-IDEMPOTENCY", occurred_at=stamp, answers={"question": "SECRET-ANSWER"}))
        db.add(UserSkill(user_id=owner.id, skill_id="python.variables", evidence_count=2,
            knowledge_score=0.5, independent_score=0.4, retention_score=0.8, next_review_at=NOW - timedelta(days=2)))
        db.commit()
        before = counts(db)
    response = client.get("/learning/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["period"] == {"active_days": 1, "lessons_completed": 1, "checks_attempted": 2, "checks_passed": 1,
        "coding_submissions": 1, "acquisition_observations": 2, "independent_observations": 1,
        "assisted_observations": 1, "review_observations": 1}
    assert body["days"][-1]["activity_count"] == 5  # source facts, not attached evidence twice
    variables = next(item for item in body["skills"] if item["skill_id"] == "python.variables")
    assert variables["acquisition_observations"] == 2 and variables["review_observations"] == 1
    assert variables["retention_score"] == 0.8 and body["totals"]["due_reviews"] == 1
    coding = next(item for item in body["recent_activity"] if item["kind"] == "coding")
    assert coding["outcome"] == "unavailable" and coding["evidence_recorded"] is False
    assert coding["assisted"] is None and coding["hint_count"] is None
    review = next(item for item in body["recent_activity"] if item["kind"] == "review")
    assert review["evidence_recorded"] is True and review["outcome"] == "correct"
    assert {item["outcome"] for item in body["recent_activity"] if item["kind"] == "knowledge_check"} == {"passed", "failed"}
    assert "SECRET" not in response.text
    for private_key in ("source_code", "answer", "metadata", "exercise_version_id", "idempotency_key"):
        assert private_key not in response.text
    assert client.get("/learning/progress").json() == body
    with database() as db:
        assert counts(db) == before


@pytest.mark.parametrize("offset,previous,current", [
    (120, datetime(2026, 10, 5, 21, 59, tzinfo=timezone.utc), datetime(2026, 10, 5, 22, tzinfo=timezone.utc)),
    (-300, datetime(2026, 10, 6, 4, 59, tzinfo=timezone.utc), datetime(2026, 10, 6, 5, tzinfo=timezone.utc)),
])
def test_fixed_offset_midnight_and_future_exclusion(client, offset, previous, current):
    setup_user(client)
    with database() as db:
        owner, version = seeded(db)
        add_check(db, owner, version, previous)
        add_check(db, owner, version, current, assisted=True)
        add_check(db, owner, version, NOW - timedelta(days=8))
        add_check(db, owner, version, NOW + timedelta(seconds=1))
        db.commit()
    body = client.get(f"/learning/progress?utc_offset_minutes={offset}").json()
    assert body["window"]["start_date"] == "2026-09-30" and body["window"]["end_date"] == "2026-10-06"
    assert body["period"]["acquisition_observations"] == 2 and body["period"]["active_days"] == 2
    assert body["days"][-2]["independent_observations"] == 1 and body["days"][-1]["assisted_observations"] == 1
    assert len(body["recent_activity"]) == 2


def test_offset_changes_window_end_date_and_lower_bound(client, monkeypatch):
    setup_user(client)
    monkeypatch.setattr(study_progress, "_utc_now", lambda: datetime(2026, 10, 6, 0, 30, tzinfo=timezone.utc))
    with database() as db:
        owner, version = seeded(db)
        add_check(db, owner, version, datetime(2026, 9, 29, 5, tzinfo=timezone.utc))
        add_check(db, owner, version, datetime(2026, 9, 29, 4, 59, tzinfo=timezone.utc))
        db.commit()
    body = client.get("/learning/progress?utc_offset_minutes=-300").json()
    assert body["window"]["start_date"] == "2026-09-29" and body["window"]["end_date"] == "2026-10-05"
    assert body["period"]["checks_attempted"] == 1 and body["days"][0]["acquisition_observations"] == 1


def test_ownership_and_future_completions_do_not_open_path(client):
    setup_user(client)
    with database() as db:
        owner, version = seeded(db)
        other = User(email="other@example.com", password_hash="unused")
        db.add(other)
        db.flush()
        add_check(db, other, version, NOW - timedelta(hours=1))
        add_check(db, owner, version, NOW + timedelta(seconds=1))
        db.add(LessonCompletion(user_id=owner.id, lesson_id="variables-v2", exercise_version_id=version.id,
                                answer="secret", completed_at=NOW + timedelta(seconds=1)))
        db.add(UserSkill(user_id=other.id, skill_id="python.variables", evidence_count=1, next_review_at=NOW - timedelta(days=1)))
        db.commit()
    body = client.get("/learning/progress").json()
    assert body["totals"]["observed_skills"] == body["totals"]["completed_lessons"] == body["totals"]["due_reviews"] == 0
    assert body["recent_activity"] == [] and body["period"]["acquisition_observations"] == 0
    assert client.get("/learning/today").json()["next_lesson"]["id"] == "variables-v2"


def test_exact_historical_snapshot_title_and_completion_alias(client):
    setup_user(client)
    with database() as db:
        owner, _ = seeded(db)
        version = _seed_exercise(db, "variables-v1", seed_hints=False)
        snapshot = deepcopy(version.content_snapshot)
        snapshot["lesson"]["title"] = "Исторический заголовок сохранённой публикации"
        version.content_snapshot = snapshot
        db.add(LessonCompletion(user_id=owner.id, lesson_id="variables-v1", exercise_version_id=version.id,
                                answer="6", completed_at=NOW - timedelta(hours=1)))
        db.commit()
        expected = learning_path(db, owner)
        db.rollback()
    body = client.get("/learning/progress").json()
    assert body["totals"]["completed_lessons"] == expected.completed == 1
    assert body["recent_activity"][0]["title"] == snapshot["lesson"]["title"]
    assert body["recent_activity"][0]["lesson_id"] == "variables-v1"
    assert body["recent_activity"][0]["skill_id"] == "python.variables"
    variables = next(item for item in body["skills"] if item["skill_id"] == "python.variables")
    assert variables["lesson_id"] == "variables-v2" and variables["lesson_status"] == "completed"
    assert variables["knowledge_score"] is None


def test_pending_historical_resume_and_mastery_path_parity(client):
    setup_user(client)
    with database() as db:
        owner, _ = seeded(db)
        version = _seed_exercise(db, "variables-v1", seed_hints=False)
        db.add(LessonSession(user_id=owner.id, lesson_id="variables-v1", exercise_version_id=version.id,
                             created_at=NOW - timedelta(hours=1)))
        db.add(UserSkill(user_id=owner.id, skill_id="python.variables", evidence_count=1,
                         independent_score=1.0, knowledge_score=1.0, practice_score=1.0))
        db.commit()
        path = learning_path(db, owner)
        readiness = prerequisite_state(db, owner.id)
        db.rollback()
    today = client.get("/learning/today").json()
    assert today["next_lesson"]["id"] == path.resume_lesson_id == "variables-v1"
    assert today["next_lesson"]["is_resume"] is True and today["focus"][0]["lesson_id"] == "variables-v1"
    body = client.get("/learning/progress").json()
    by_lesson = {item["lesson_id"]: item["lesson_status"] for item in body["skills"]}
    assert all(by_lesson[item.id] == item.status for item in path.lessons)
    assert readiness.is_lesson_ready(LESSONS_BY_ID["data-types-v2"])


def test_legacy_readiness_parity_and_unknown_completion_not_primary(client):
    setup_user(client)
    with database() as db:
        owner, _ = seeded(db)
        for lesson_id in ("variables-v1", "data-types-v2"):
            db.add(LessonCompletion(user_id=owner.id, lesson_id=lesson_id, answer="6", completed_at=NOW - timedelta(hours=1)))
        db.commit()
        path = learning_path(db, owner)
        db.rollback()
    body = client.get("/learning/progress").json()
    by_lesson = {item["lesson_id"]: item["lesson_status"] for item in body["skills"]}
    assert all(by_lesson[item.id] == item.status for item in path.lessons)
    assert by_lesson["conditions-v2"] == "locked" and body["totals"]["completed_lessons"] == 2


def test_today_filters_locked_completed_unknown_unavailable_and_duplicate_curriculum(client):
    setup_user(client)
    with database() as db:
        owner, version = seeded(db)
        db.add(LessonCompletion(user_id=owner.id, lesson_id="variables-v2", exercise_version_id=version.id,
                                answer="done", completed_at=NOW - timedelta(hours=1)))
        plan = LearningPlan(user_id=owner.id, recommendation_text="test")
        db.add(plan)
        db.flush()
        revision = CurriculumPlanRevision(plan_id=plan.id, version=1, as_of=NOW - timedelta(hours=1),
                                           goal_snapshot={}, coverage={}, reason="test")
        db.add(revision)
        db.flush()
        session = CurriculumSession(revision_id=revision.id, position=1, target_minutes=60, planned_minutes=60, rationale="test")
        db.add(session)
        db.flush()
        entries = [("variables-v2", "python.variables", "available"), ("conditions-v2", "python.conditionals", "available"),
                   ("missing", "missing", "available"), ("data-types-v2", "python.data_types", "unavailable"),
                   ("data-types-v2", "python.data_types", "available"), ("data-types-v2", "python.data_types", "available")]
        for position, (lesson_id, skill_id, availability) in enumerate(entries, 1):
            db.add(CurriculumActivity(session_id=session.id, position=position, kind="lesson", lesson_id=lesson_id,
                skill_id=skill_id, availability=availability, estimated_minutes=12, priority=0.2, reason_codes=["skill_gap"]))
        db.commit()
        before = counts(db)
    today = client.get("/learning/today").json()
    assert today["source"] == "curriculum" and [item["lesson_id"] for item in today["focus"]] == ["data-types-v2"]
    assert today["estimated_minutes"] == 12 and today["target_minutes"] == 60 and "status" not in today
    with database() as db:
        assert counts(db) == before and db.scalar(select(CurriculumSession)).status == "planned"


def test_due_reviews_match_existing_eligibility_without_starting_sessions(client):
    setup_user(client)
    with database() as db:
        owner, _ = seeded(db)
        for skill_id, due_at in (("python.variables", NOW - timedelta(days=2)), ("python.conditionals", NOW - timedelta(days=1)),
                                 ("python.loops", NOW + timedelta(days=1)), ("unknown.skill", NOW - timedelta(days=1))):
            db.add(UserSkill(user_id=owner.id, skill_id=skill_id, evidence_count=1, next_review_at=due_at))
        db.commit()
        before = counts(db)
        expected = study_progress._due_rows(db, owner, now=NOW)
    today = client.get("/learning/today").json()
    assert [item["skill_id"] for item in today["due_reviews"]] == [row.skill_id for row, _ in expected]
    assert today["due_reviews"][0]["overdue_days"] == 2
    assert client.get("/learning/progress").json()["totals"]["due_reviews"] == 2
    with database() as db:
        assert counts(db) == before


def test_unfinished_assessment_is_activity_without_acquisition_credit(client):
    setup_user(client)
    with database() as db:
        owner, _ = seeded(db)
        run = AssessmentRun(user_id=owner.id, status="in_progress")
        db.add(run)
        db.flush()
        db.add(AssessmentResponse(run_id=run.id, question_id="persisted-question", skill_id="python.variables",
            difficulty=0.1, answer="SECRET-ANSWER", is_correct=False, created_at=NOW - timedelta(hours=1)))
        db.commit()
    body = client.get("/learning/progress").json()
    assert body["period"]["active_days"] == 1 and body["period"]["acquisition_observations"] == 0
    assert body["days"][-1]["activity_count"] == 1
    assert all(item["activity_count"] == 0 for item in body["days"][:-1])
    assert body["recent_activity"][0]["kind"] == "assessment" and body["recent_activity"][0]["evidence_recorded"] is False
    assert body["recent_activity"][0]["outcome"] == "incorrect"


def test_bounded_queries_and_exact_counts_beyond_recent_limit(client):
    setup_user(client)
    with database() as db:
        owner, version = seeded(db)
        for index in range(75):
            add_check(db, owner, version, NOW - timedelta(minutes=index + 1))
        db.commit()
        engine = db.get_bind()
    statements = []
    def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", observe)
    try:
        response = client.get("/learning/progress")
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert response.status_code == 200
    body = response.json()
    assert body["period"]["checks_attempted"] == body["period"]["acquisition_observations"] == 75
    assert len(body["recent_activity"]) == 50 and len(statements) < 35
    # Authentication's existing last_seen_at refresh is separate from the
    # learner domain. These reads may not mutate any learning table.
    writes = [sql for sql in statements if sql.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}]
    assert all(sql.lstrip().startswith("UPDATE auth_sessions SET last_seen_at=") for sql in writes)
    history_reads = [sql for sql in statements if "ORDER BY" in sql and any(
        name in sql for name in ("knowledge_check_attempts", "coding_attempts", "assessment_responses", "review_attempts"))]
    assert history_reads and all("LIMIT" in sql for sql in history_reads)


def test_current_persisted_publication_wins_over_mutable_authoring(client):
    setup_user(client)
    with database() as db:
        owner, version = seeded(db)
        snapshot = deepcopy(version.content_snapshot)
        snapshot["lesson"]["title"] = "Заголовок точной опубликованной версии"
        version.content_snapshot = snapshot
        db.commit()
        path = learning_path(db, owner)
        db.rollback()
    today = client.get("/learning/today").json()
    assert today["next_lesson"]["title"] == path.lessons[0].title == snapshot["lesson"]["title"]


def test_missing_existing_publication_snapshot_is_controlled_and_not_rebuilt(client):
    setup_user(client)
    with database() as db:
        _, version = seeded(db)
        version.content_snapshot = None
        db.commit()
        before = counts(db)
    for path in ("/learning/progress", "/learning/today"):
        response = client.get(path)
        assert response.status_code == 409
        assert response.json() == {"detail": "Lesson content snapshot is unavailable"}
    with database() as db:
        assert counts(db) == before
        assert db.scalar(select(study_progress.ExerciseVersion).where(
            study_progress.ExerciseVersion.exercise_id == "variables-v2")).content_snapshot is None
