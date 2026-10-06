from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.curriculum import build_curriculum
from app.db.models import (
    ExerciseHint,
    ExerciseVersion,
    Goal,
    HintReveal,
    LearningPlan,
    LearningPlanItem,
    LessonCompletion,
    ReviewAttempt,
    SkillEvidence,
    User,
    UserSkill,
)
from app.db.session import get_db
from app.main import app
from app.learning_content import LESSONS
from test_auth import client, csrf


def setup_user(c, email="reviews@example.com", weekly_minutes=180):
    assert c.post(
        "/auth/register",
        json={"email": email, "password": "safe-password"},
    ).status_code == 201
    assert c.post(
        "/onboarding",
        headers={"X-CSRF-Token": csrf(c)},
        json={
            "experience_level": "beginner",
            "target_role": "Python Backend",
            "weekly_minutes": weekly_minutes,
        },
    ).status_code == 200


def add_due_skill(c, skill_id="python.variables", days=-2):
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        db.add(
            UserSkill(
                user_id=user.id,
                skill_id=skill_id,
                knowledge_score=0.5,
                practice_score=0.5,
                independent_score=0.5,
                evidence_count=1,
                next_review_at=datetime.now(timezone.utc) + timedelta(days=days),
            )
        )
        db.commit()


def test_review_api_is_owned_csrf_protected_and_server_graded(client):
    assert client.get("/learning/reviews/due").status_code == 401
    setup_user(client)
    assert client.get("/learning/reviews/due").json() == {"items": []}
    add_due_skill(client)

    due = client.get("/learning/reviews/due")
    assert due.status_code == 200
    assert due.json()["items"][0]["skill_id"] == "python.variables"
    assert "user_id" not in due.text
    assert "exercise_version_id" not in due.text

    assert client.post(
        "/learning/reviews/session/start",
        json={"skill_id": "python.variables"},
    ).status_code == 403
    assert client.post(
        "/learning/reviews/session/start",
        headers={"X-CSRF-Token": csrf(client)},
        json={"skill_id": "python.variables", "grade": 1},
    ).status_code == 422

    started = client.post(
        "/learning/reviews/session/start",
        headers={"X-CSRF-Token": csrf(client)},
        json={"skill_id": "python.variables"},
    )
    assert started.status_code == 201
    body = started.json()
    assert len(body["session_token"]) >= 32
    assert "answer" not in started.text
    assert "exercise_version_id" not in started.text
    assert "version" not in started.text
    assert set(body["question"]) == {"id", "prompt", "choices"}
    answers = {
        "variables-text-v2": "Текст books",
        "variables-order-v2": "7",
    }

    assert client.post(
        "/learning/reviews/answer",
        headers={"X-CSRF-Token": csrf(client)},
        json={
            "session_token": body["session_token"],
            "answers": answers,
            "score": 0,
        },
    ).status_code == 422
    answer = client.post(
        "/learning/reviews/answer",
        headers={"X-CSRF-Token": csrf(client)},
        json={"session_token": body["session_token"], "answers": answers},
    )
    assert answer.status_code == 200
    assert answer.json()["correct"] is True
    assert answer.json()["score"] == 1.0

    replay = client.post(
        "/learning/reviews/answer",
        headers={"X-CSRF-Token": csrf(client)},
        json={"session_token": body["session_token"], "answers": answers},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True

    with next(app.dependency_overrides[get_db]()) as db:
        attempts = db.scalars(select(ReviewAttempt)).all()
        evidence = db.scalars(select(SkillEvidence)).all()
        assert len(attempts) == 1
        assert len(evidence) == 1
        assert evidence[0].source_type == "review_attempt"
        assert evidence[0].retention_only is True
        assert attempts[0].answers == answers


def test_today_contract_is_public_and_replays_without_duplicate_evidence(client):
    setup_user(client, "reviews-today@example.com")
    add_due_skill(client, days=-2)

    assert client.get("/learning/reviews/today").status_code == 200
    today = client.get("/learning/reviews/today")
    assert today.status_code == 200
    body = today.json()
    assert set(body) == {"as_of", "items"}
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert set(item) == {
        "review_token",
        "skill_id",
        "scheduled_for",
        "overdue_days",
        "questions",
    }
    assert item["overdue_days"] >= 1
    assert all(set(question) == {"id", "prompt", "choices"} for question in item["questions"])
    for forbidden in (
        "answer",
        "score",
        "assisted",
        "hint_count",
        "interval",
        "user_id",
        "exercise_version_id",
        "session_id",
    ):
        assert forbidden not in today.text

    answers = {
        "variables-text-v2": "Текст books",
        "variables-order-v2": "7",
    }
    headers = {
        "X-CSRF-Token": csrf(client),
        "Idempotency-Key": "today-contract-1",
    }
    assert client.post(
        "/learning/reviews/today/complete",
        headers=headers,
        json={"review_token": item["review_token"], "answers": answers, "score": 1},
    ).status_code == 422
    assert client.post(
        "/learning/reviews/today/complete",
        headers={"Idempotency-Key": "today-contract-1"},
        json={"review_token": item["review_token"], "answers": answers},
    ).status_code == 403

    completed = client.post(
        "/learning/reviews/today/complete",
        headers=headers,
        json={"review_token": item["review_token"], "answers": answers},
    )
    assert completed.status_code == 200
    assert set(completed.json()) == {
        "status",
        "outcome",
        "schedule_applied",
        "same_day",
        "next_review_at",
    }
    assert completed.json()["status"] == "recorded"
    assert completed.json()["outcome"] == "correct"
    assert completed.json()["schedule_applied"] is True
    assert completed.json()["same_day"] is False

    replay = client.post(
        "/learning/reviews/today/complete",
        headers=headers,
        json={"review_token": item["review_token"], "answers": answers},
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "replayed"
    with next(app.dependency_overrides[get_db]()) as db:
        assert len(db.scalars(select(ReviewAttempt)).all()) == 1
        assert len(db.scalars(select(SkillEvidence)).all()) == 1


def test_today_completion_uses_server_hint_attribution_and_same_day_is_observation_only(client):
    setup_user(client, "reviews-today-hints@example.com")
    add_due_skill(client, days=-1)
    headers = {"X-CSRF-Token": csrf(client)}
    first = client.get("/learning/reviews/today")
    assert first.status_code == 200
    first_item = first.json()["items"][0]

    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        version = db.scalar(select(ExerciseVersion))
        hint = db.scalar(
            select(ExerciseHint).where(ExerciseHint.exercise_version_id == version.id)
        )
        db.add(
            HintReveal(
                user_id=user.id,
                exercise_version_id=version.id,
                hint_id=hint.id,
                level=hint.level,
                idempotency_key="review-today-hint-1",
                revealed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    answers = {
        "variables-text-v2": "Текст books",
        "variables-order-v2": "7",
    }
    completed = client.post(
        "/learning/reviews/today/complete",
        headers={**headers, "Idempotency-Key": "today-hints-1"},
        json={"review_token": first_item["review_token"], "answers": answers},
    )
    assert completed.status_code == 200
    assert "assisted" not in completed.text
    assert "hint_count" not in completed.text

    with next(app.dependency_overrides[get_db]()) as db:
        mastery = db.scalar(select(UserSkill))
        mastery.next_review_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    second = client.get("/learning/reviews/today")
    assert second.status_code == 200
    second_item = second.json()["items"][0]
    second_completed = client.post(
        "/learning/reviews/today/complete",
        headers={**headers, "Idempotency-Key": "today-hints-2"},
        json={"review_token": second_item["review_token"], "answers": answers},
    )
    assert second_completed.status_code == 200
    assert second_completed.json()["schedule_applied"] is False
    assert second_completed.json()["same_day"] is True

    with next(app.dependency_overrides[get_db]()) as db:
        evidence = db.scalars(select(SkillEvidence)).all()
        attempts = db.scalars(select(ReviewAttempt)).all()
        mastery = db.scalar(select(UserSkill))
        assert len(evidence) == len(attempts) == 2
        assert all(row.source_type == "review_attempt" for row in evidence)
        assert all(row.retention_only for row in evidence)
        assert evidence[0].assisted is True
        assert evidence[0].hint_count == 1
        assert len([row for row in attempts if row.applied_on is not None]) == 1
        assert mastery.next_review_at is not None


def test_review_binds_snapshot_and_derives_hint_assistance_on_server(client):
    setup_user(client, "review-snapshot@example.com")
    add_due_skill(client, days=-1)
    started = client.post(
        "/learning/reviews/session/start",
        headers={"X-CSRF-Token": csrf(client)},
        json={"skill_id": "python.variables"},
    )
    assert started.status_code == 201
    token = started.json()["session_token"]

    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        session = db.scalar(select(ExerciseVersion))
        hint = db.scalar(
            select(ExerciseHint).where(ExerciseHint.exercise_version_id == session.id)
        )
        db.add(
            HintReveal(
                user_id=user.id,
                exercise_version_id=session.id,
                hint_id=hint.id,
                level=hint.level,
                idempotency_key="review-api-test-hint",
                revealed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    from app.learning_content import LESSONS_BY_ID
    authored = LESSONS_BY_ID["variables-v2"]
    original_answer = authored["answer"]
    authored["answer"] = "На экран попадёт число 2"
    try:
        response = client.post(
            "/learning/reviews/answer",
            headers={"X-CSRF-Token": csrf(client)},
            json={
                "session_token": token,
                "answers": {
                    "variables-text-v2": "Текст books",
                    "variables-order-v2": "7",
                },
            },
        )
    finally:
        authored["answer"] = original_answer
    assert response.status_code == 200
    assert response.json()["correct"] is True
    assert response.json()["assisted"] is True
    assert response.json()["hint_count"] == 1


def test_same_utc_day_retains_later_observation_without_second_shift(client):
    setup_user(client, "review-same-day@example.com")
    add_due_skill(client, days=-1)
    headers = {"X-CSRF-Token": csrf(client)}
    first = client.post(
        "/learning/reviews/session/start",
        headers=headers,
        json={"skill_id": "python.variables"},
    ).json()
    first_answer = client.post(
        "/learning/reviews/answer",
        headers=headers,
        json={
            "session_token": first["session_token"],
            "answers": {
                "variables-text-v2": "Текст books",
                "variables-order-v2": "7",
            },
        },
    )
    assert first_answer.status_code == 200

    with next(app.dependency_overrides[get_db]()) as db:
        mastery = db.scalar(select(UserSkill))
        mastery.next_review_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        due_before_second = mastery.next_review_at
        unchanged_projection = (
            mastery.knowledge_score,
            mastery.independent_score,
            mastery.practice_score,
            mastery.mastery_weight,
            mastery.confidence,
            mastery.evidence_count,
        )
        db.commit()

    second = client.post(
        "/learning/reviews/session/start",
        headers=headers,
        json={"skill_id": "python.variables"},
    )
    assert second.status_code == 201
    second_answer = client.post(
        "/learning/reviews/answer",
        headers=headers,
        json={
            "session_token": second.json()["session_token"],
            "answers": {
                "variables-text-v2": "Число из переменной books",
                "variables-order-v2": "4",
            },
        },
    )
    assert second_answer.status_code == 200
    returned_due = datetime.fromisoformat(second_answer.json()["next_review_at"])
    assert abs((returned_due - due_before_second.replace(tzinfo=None)).total_seconds()) < 2

    with next(app.dependency_overrides[get_db]()) as db:
        attempts = db.scalars(select(ReviewAttempt)).all()
        evidence = db.scalars(select(SkillEvidence)).all()
        mastery = db.scalar(select(UserSkill))
        assert len(attempts) == len(evidence) == 2
        assert all(row.source_type == "review_attempt" for row in evidence)
        assert all(row.retention_only for row in evidence)
        assert len([row for row in attempts if row.applied_on is not None]) == 1
        assert (
            mastery.knowledge_score,
            mastery.independent_score,
            mastery.practice_score,
            mastery.mastery_weight,
            mastery.confidence,
            mastery.evidence_count,
        ) == unchanged_projection
        assert mastery.next_review_at.replace(tzinfo=None) == returned_due.replace(tzinfo=None)


def test_overdue_review_is_bounded_and_appended_after_learning_candidates(client):
    setup_user(client, "review-plan@example.com", weekly_minutes=30)
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        now = datetime.now(timezone.utc)
        plan = LearningPlan(
            user_id=user.id,
            recommendation_text="test",
            version=1,
            generated_at=now,
        )
        db.add(plan)
        db.flush()
        db.add(
            LearningPlanItem(
                plan_id=plan.id,
                lesson_id="variables-v1",
                skill_id="python.variables",
                position=1,
                focus_score=0.5,
                rationale="test",
            )
        )
        db.add(LessonCompletion(
            user_id=user.id,
            lesson_id="variables-v1",
            answer="6",
            completed_at=now,
        ))
        db.add(LessonCompletion(
            user_id=user.id,
            lesson_id="data-types-v1",
            answer="types",
            completed_at=now,
        ))
        db.add(UserSkill(
            user_id=user.id,
            skill_id="python.variables",
            knowledge_score=0.5,
            practice_score=0.5,
            independent_score=0.5,
            evidence_count=1,
            next_review_at=now - timedelta(days=10),
        ))
        db.add(UserSkill(
            user_id=user.id,
            skill_id="python.data_types",
            knowledge_score=0.9,
            practice_score=0.9,
            independent_score=0.9,
            evidence_count=1,
        ))
        db.flush()
        revision = build_curriculum(db, user, reason="review_test")
        db.commit()
        assert revision is not None

    curriculum = client.get("/learning/curriculum")
    assert curriculum.status_code == 200
    activities = curriculum.json()["sessions"][-1]["activities"]
    assert activities[0]["kind"] == "lesson"
    assert activities[0]["skill_id"] == "python.conditionals"
    review = next(item for item in activities if item["kind"] == "review")
    assert review["skill_id"] == "python.variables"
    assert review["priority"] <= 0.30
