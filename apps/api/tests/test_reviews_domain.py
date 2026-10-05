from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import ReviewAttempt, SkillEvidence, SkillMasteryAudit, User, UserSkill
from app.db.session import get_db
from app.main import app
from app.reviews import ReviewHistoryItem, review_interval_days
from test_auth import client, csrf


def setup_review_user(c):
    assert c.post(
        "/auth/register",
        json={"email": "review-domain@example.com", "password": "safe-password"},
    ).status_code == 201
    assert c.post(
        "/onboarding",
        headers={"X-CSRF-Token": csrf(c)},
        json={
            "experience_level": "beginner",
            "target_role": "Python Backend",
            "weekly_minutes": 180,
        },
    ).status_code == 200


def add_due_skill(c):
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        db.add(
            UserSkill(
                user_id=user.id,
                skill_id="python.variables",
                knowledge_score=0.4,
                practice_score=0.3,
                independent_score=0.2,
                retention_score=0.1,
                confidence=0.8,
                mastery_weight=2.0,
                evidence_count=4,
                next_review_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )
        db.commit()


def review_answers(correct=True):
    return {
        "variables-output-v1": "6" if correct else "4",
        "variables-reassignment-v1": (
            "Увеличивает текущее значение x на 1"
            if correct
            else "Создаёт вторую переменную x"
        ),
    }


def test_review_policy_uses_conservative_explainable_intervals():
    assert review_interval_days(result_score=1, assisted=False) == 7
    assert review_interval_days(result_score=0.5, assisted=False) == 1
    assert review_interval_days(result_score=1, assisted=True) == 3
    assert review_interval_days(
        result_score=1,
        assisted=False,
        prior_reviews=[
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True)
        ],
    ) == 14
    assert review_interval_days(
        result_score=1,
        assisted=False,
        prior_reviews=[
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True),
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True),
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True),
        ],
    ) == 60
    assert review_interval_days(
        result_score=1,
        assisted=False,
        prior_reviews=[
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=False),
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True),
        ],
    ) == 14
    assert review_interval_days(
        result_score=1,
        assisted=False,
        prior_reviews=[
            ReviewHistoryItem(result_score=0.5, assisted=False, schedule_applied=True),
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True),
        ],
    ) == 7


def test_review_policy_covers_all_supported_intervals():
    assert review_interval_days(result_score=0, assisted=False) == 1
    assert review_interval_days(result_score=1, assisted=True) == 3
    assert review_interval_days(result_score=1, assisted=False) == 7
    assert review_interval_days(
        result_score=1,
        assisted=False,
        prior_reviews=[
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True)
        ],
    ) == 14
    assert review_interval_days(
        result_score=1,
        assisted=False,
        prior_reviews=[
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True),
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True),
        ],
    ) == 30
    assert review_interval_days(
        result_score=1,
        assisted=False,
        prior_reviews=[
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True),
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True),
            ReviewHistoryItem(result_score=1, assisted=False, schedule_applied=True),
        ],
    ) == 60


def test_review_is_retention_only_and_does_not_change_knowledge_projection(client):
    setup_review_user(client)
    add_due_skill(client)

    with next(app.dependency_overrides[get_db]()) as db:
        before = db.scalar(select(UserSkill))
        before_values = {
            name: getattr(before, name)
            for name in (
                "knowledge_score",
                "independent_score",
                "practice_score",
                "mastery_weight",
                "confidence",
                "evidence_count",
            )
        }

    headers = {"X-CSRF-Token": csrf(client)}
    started = client.post(
        "/learning/reviews/session/start",
        headers=headers,
        json={"skill_id": "python.variables"},
    )
    assert started.status_code == 201
    answer = client.post(
        "/learning/reviews/answer",
        headers=headers,
        json={
            "session_token": started.json()["session_token"],
            "answers": review_answers(),
        },
    )
    assert answer.status_code == 200
    assert answer.json()["interval_days"] == 7

    with next(app.dependency_overrides[get_db]()) as db:
        after = db.scalar(select(UserSkill))
        after_values = {
            name: getattr(after, name)
            for name in before_values
        }
        evidence = db.scalar(select(SkillEvidence))
        attempt = db.scalar(select(ReviewAttempt))
        assert after_values == before_values
        assert evidence.source_type == "review_attempt"
        assert evidence.retention_only is True
        assert evidence.assisted is False
        assert evidence.hint_count == 0
        assert attempt.skill_evidence_id == evidence.id
        audit = db.scalar(select(SkillMasteryAudit).where(
            SkillMasteryAudit.evidence_id == evidence.id
        ))
        assert audit.before_evidence_count == audit.after_evidence_count
        assert audit.before_mastery == audit.after_mastery
        attempt_time = attempt.occurred_at
        next_review_at = after.next_review_at
        if attempt_time.tzinfo is None:
            attempt_time = attempt_time.replace(tzinfo=timezone.utc)
        if next_review_at.tzinfo is None:
            next_review_at = next_review_at.replace(tzinfo=timezone.utc)
        assert next_review_at - attempt_time == timedelta(days=7)


def test_same_day_replay_is_idempotent_and_does_not_shift_again(client):
    setup_review_user(client)
    add_due_skill(client)
    headers = {"X-CSRF-Token": csrf(client)}

    started = client.post(
        "/learning/reviews/session/start",
        headers=headers,
        json={"skill_id": "python.variables"},
    )
    token = started.json()["session_token"]
    payload = {
        "session_token": token,
        "answers": review_answers(),
    }
    first = client.post(
        "/learning/reviews/answer",
        headers={**headers, "Idempotency-Key": "same-day-key"},
        json=payload,
    )
    assert first.status_code == 200
    replay = client.post(
        "/learning/reviews/answer",
        headers={**headers, "Idempotency-Key": "same-day-key"},
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True

    with next(app.dependency_overrides[get_db]()) as db:
        assert len(db.scalars(select(ReviewAttempt)).all()) == 1
        assert len(db.scalars(select(SkillEvidence)).all()) == 1

    changed_payload = {
        "session_token": token,
        "answers": review_answers(correct=False),
    }
    reused = client.post(
        "/learning/reviews/answer",
        headers={**headers, "Idempotency-Key": "same-day-key"},
        json=changed_payload,
    )
    assert reused.status_code == 409
