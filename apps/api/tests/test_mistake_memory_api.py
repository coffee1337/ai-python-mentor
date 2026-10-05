from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.db.models import Misconception, MisconceptionVersion, User, UserMistake
from app.db.session import get_db
from app.main import app
from test_auth import client, csrf


def _setup_user(test_client, email):
    assert (
        test_client.post(
            "/auth/register",
            json={"email": email, "password": "safe-password"},
        ).status_code
        == 201
    )
    assert (
        test_client.post(
            "/onboarding",
            headers={"X-CSRF-Token": csrf(test_client)},
            json={
                "experience_level": "beginner",
                "target_role": "Python Backend",
                "weekly_minutes": 180,
            },
        ).status_code
        == 200
    )


def _seed_mistake(db, *, user_id, code, error_text, count, last_seen_at):
    db.add(
        Misconception(
            code=code,
            skill_id=f"skill.{code}",
        )
    )
    db.add(
        MisconceptionVersion(
            id=uuid4(),
            misconception_code=code,
            version=1,
            error_text=error_text,
            typical_wrong_explanation="internal explanation",
            remediation_text=f"Remediation for {code}",
            remediation_exercise_id=f"{code}-exercise",
            remediation_exercise_version=1,
        )
    )
    db.add(
        UserMistake(
            user_id=user_id,
            misconception_code=code,
            skill_id=f"skill.{code}",
            lesson_id=f"{code}-lesson",
            occurrence_count=count,
            first_seen_at=last_seen_at - timedelta(days=1),
            last_seen_at=last_seen_at,
            last_source_type="knowledge_check_response",
            last_source_id=str(uuid4()),
        )
    )


def test_get_mistakes_returns_empty_for_authenticated_user(client):
    _setup_user(client, "mistakes-empty@example.com")

    response = client.get("/learning/mistakes")

    assert response.status_code == 200
    assert response.json() == []


def test_get_mistakes_returns_only_own_repeated_rows_and_public_fields(client):
    _setup_user(client, "mistakes-own@example.com")
    last_seen = datetime(2026, 10, 2, 12, 30, tzinfo=timezone.utc)
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(
            select(User).where(User.email == "mistakes-own@example.com")
        )
        _seed_mistake(
            db,
            user_id=user.id,
            code="repeated-own",
            error_text="Own repeated error",
            count=2,
            last_seen_at=last_seen,
        )
        _seed_mistake(
            db,
            user_id=user.id,
            code="single-own",
            error_text="Own single error",
            count=1,
            last_seen_at=last_seen,
        )
        db.commit()

    response = client.get("/learning/mistakes")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "error_text": "Own repeated error",
            "remediation_text": "Remediation for repeated-own",
            "remediation_exercise_id": "repeated-own-exercise",
            "last_seen_at": "2026-10-02T12:30:00",
        }
    ]
    assert set(body[0]) == {
        "error_text",
        "remediation_text",
        "remediation_exercise_id",
        "last_seen_at",
    }
    assert "occurrence_count" not in response.text
    assert "internal explanation" not in response.text
    assert "last_source_id" not in response.text


def test_get_mistakes_ignores_requested_user_id_and_isolates_current_user(client):
    _setup_user(client, "mistakes-owner@example.com")
    with next(app.dependency_overrides[get_db]()) as db:
        owner = db.scalar(
            select(User).where(User.email == "mistakes-owner@example.com")
        )
        owner_id = owner.id
        _seed_mistake(
            db,
            user_id=owner_id,
            code="owner-only",
            error_text="Owner error",
            count=2,
            last_seen_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )
        db.commit()

    assert (
        client.post(
            "/auth/logout",
            headers={"X-CSRF-Token": csrf(client)},
        ).status_code
        == 204
    )
    _setup_user(client, "mistakes-other@example.com")
    with next(app.dependency_overrides[get_db]()) as db:
        other = db.scalar(
            select(User).where(User.email == "mistakes-other@example.com")
        )
        _seed_mistake(
            db,
            user_id=other.id,
            code="other-only",
            error_text="Other error",
            count=2,
            last_seen_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )
        db.commit()

    response = client.get(f"/learning/mistakes?user_id={owner_id}")

    assert response.status_code == 200
    assert [item["error_text"] for item in response.json()] == ["Other error"]
    assert "Owner error" not in response.text
