from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import ReviewAttempt, SkillEvidence, User, UserSkill
from app.db.session import get_db
from app.main import app
from test_auth import client, csrf


def setup_user(c, email: str) -> None:
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
            "weekly_minutes": 180,
        },
    ).status_code == 200


def add_due_skill() -> None:
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User).order_by(User.created_at.desc()))
        db.add(
            UserSkill(
                user_id=user.id,
                skill_id="python.variables",
                knowledge_score=0.5,
                practice_score=0.5,
                independent_score=0.5,
                evidence_count=1,
                next_review_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )
        db.commit()


def review_answers() -> dict[str, str]:
    return {
        "variables-output-v1": "6",
        "variables-reassignment-v1": "Увеличивает текущее значение x на 1",
    }


def test_review_token_is_owned_by_authenticated_user_and_post_requires_csrf(client):
    setup_user(client, "review-owner-a@example.com")
    add_due_skill()
    item = client.get("/learning/reviews/today").json()["items"][0]
    owner_token = item["review_token"]

    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    setup_user(client, "review-owner-b@example.com")

    assert client.post(
        "/learning/reviews/today/complete",
        headers={"Idempotency-Key": "cross-user-review"},
        json={"review_token": owner_token, "answers": review_answers()},
    ).status_code == 403

    response = client.post(
        "/learning/reviews/today/complete",
        headers={
            "X-CSRF-Token": csrf(client),
            "Idempotency-Key": "cross-user-review",
        },
        json={"review_token": owner_token, "answers": review_answers()},
    )
    assert response.status_code == 409

    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalars(select(ReviewAttempt)).all() == []
        assert db.scalars(select(SkillEvidence)).all() == []


def test_today_completion_rejects_client_derived_fields_and_internal_ids(client):
    setup_user(client, "review-contract-fields@example.com")
    add_due_skill()
    item = client.get("/learning/reviews/today").json()["items"][0]
    headers = {
        "X-CSRF-Token": csrf(client),
        "Idempotency-Key": "review-forbidden-fields",
    }

    for field, value in (
        ("user_id", "not-server-owned"),
        ("score", 1),
        ("outcome", "correct"),
        ("assisted", False),
        ("hint_count", 0),
        ("interval_days", 7),
        ("session_id", "internal"),
        ("exercise_version_id", "internal"),
    ):
        response = client.post(
            "/learning/reviews/today/complete",
            headers=headers,
            json={
                "review_token": item["review_token"],
                "answers": review_answers(),
                field: value,
            },
        )
        assert response.status_code == 422, field

    assert client.post(
        "/learning/reviews/today/complete",
        headers=headers,
        json={"review_token": item["review_token"], "answers": review_answers()},
    ).status_code == 200
