"""Saved source recovery is owner-only, version-aware, and read-only."""
from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import CodingAttempt, ExerciseVersion, Skill, SkillEvidence, UserSkill
from app.db.session import get_db
from app.main import app
from test_auth import client, csrf


PUBLIC_SOURCE_FIELDS = {
    "attempt_id", "exercise_id", "exercise_version", "source_code",
    "language", "mode", "created_at", "version_verified",
}
RECOVERY_TABLES = (
    "coding_attempts", "exercise_versions", "execution_jobs", "submission_results",
    "submission_test_results", "skill_evidence", "user_skills", "lesson_sessions",
    "hint_reveals",
)


def register(c, email="recover@example.com"):
    assert c.post(
        "/auth/register", json={"email": email, "password": "safe-password"},
    ).status_code == 201
    assert c.post(
        "/onboarding",
        headers={"X-CSRF-Token": csrf(c)},
        json={"experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180},
    ).status_code == 200


def save_attempt(c, monkeypatch, source, key="recover-saved-source"):
    monkeypatch.setenv("EXECUTION_JOBS_ENABLED", "false")
    response = c.post(
        "/learning/exercises/variables-v1-code/jobs",
        headers={"X-CSRF-Token": csrf(c), "Idempotency-Key": key},
        json={"language": "python", "mode": "function", "source_code": source},
    )
    assert response.status_code == 202
    return response.json()["attempt_id"]


def learning_state():
    with next(app.dependency_overrides[get_db]()) as db:
        return {
            name: [dict(row) for row in db.execute(
                select(Base.metadata.tables[name]).order_by(*Base.metadata.tables[name].primary_key),
            ).mappings()]
            for name in RECOVERY_TABLES
        }


def fail_if_called(*args, **kwargs):
    pytest.fail("Source recovery must not publish, execute, submit, or grade")


def test_source_recovery_requires_auth_and_an_existing_uuid(client):
    missing = f"/learning/attempts/{uuid4()}/source"
    assert client.get(missing).status_code == 401
    register(client)
    assert client.get(missing).status_code == 404
    assert client.get("/learning/attempts/not-a-uuid/source").status_code == 422


def test_owner_recovers_exact_utf8_source_after_logging_in_again(client, monkeypatch):
    register(client)
    source = 'def solve(p):\n    # Сохранённый черновик 🐍\n    return "<script>не выполнять</script>"\n'
    attempt_id = save_attempt(client, monkeypatch, source)
    save_attempt(client, monkeypatch, "def solve(p):\n    return 0\n", key="recover-second-source")
    assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)}).status_code == 204
    endpoint = f"/learning/attempts/{attempt_id}/source"
    assert client.get(endpoint).status_code == 401
    assert client.post(
        "/auth/login", json={"email": "recover@example.com", "password": "safe-password"},
    ).status_code == 200
    response = client.get(endpoint)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()
    assert set(data) == PUBLIC_SOURCE_FIELDS
    assert data["attempt_id"] == attempt_id
    assert data["exercise_id"] == "variables-v1-code"
    assert data["source_code"] == source
    assert data["language"] == "python" and data["mode"] == "function"
    assert data["exercise_version"] == 1 and data["version_verified"] is True
    assert datetime.fromisoformat(data["created_at"])


def test_source_ownership_cannot_be_bypassed_by_accessible_exercise(client, monkeypatch):
    register(client)
    attempt_id = save_attempt(client, monkeypatch, "def solve(p): return 7")
    assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)}).status_code == 204
    register(client, "another-learner@example.com")
    # This other learner can access exactly the same authored exercise.
    assert client.get("/learning/exercises/variables-v1-code/attempts").status_code == 200
    original_get = Session.get

    def no_foreign_version_lookup(db, entity, *args, **kwargs):
        if entity is ExerciseVersion:
            pytest.fail("A foreign attempt must be rejected before version lookup")
        return original_get(db, entity, *args, **kwargs)

    monkeypatch.setattr(Session, "get", no_foreign_version_lookup)
    foreign = client.get(f"/learning/attempts/{attempt_id}/source")
    missing = client.get(f"/learning/attempts/{uuid4()}/source")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert "return 7" not in foreign.text


@pytest.mark.parametrize("binding", ["null", "mismatch", "missing"])
def test_unverified_legacy_bindings_allow_preview_without_a_public_version(client, monkeypatch, binding):
    register(client)
    source = "# Мой старый код\ndef solve(p):\n    return 3\n"
    attempt_id = save_attempt(client, monkeypatch, source)
    with next(app.dependency_overrides[get_db]()) as db:
        attempt = db.get(CodingAttempt, UUID(attempt_id))
        if binding == "mismatch":
            other = ExerciseVersion(exercise_id="another-exercise", version=99, content_snapshot={"solution": "secret"})
            db.add(other)
            db.flush()
            attempt.exercise_version_id = other.id
        else:
            attempt.exercise_version_id = None if binding == "null" else uuid4()
        db.commit()
    before = learning_state()
    monkeypatch.setattr("app.coding_exercises.resolve_coding_exercise", fail_if_called)
    monkeypatch.setattr("app.practice.runner.run", fail_if_called)
    monkeypatch.setattr("app.practice.record_evidence", fail_if_called)
    response = client.get(f"/learning/attempts/{attempt_id}/source")
    assert response.status_code == 200
    assert set(response.json()) == PUBLIC_SOURCE_FIELDS
    assert response.json()["source_code"] == source
    assert response.json()["exercise_version"] is None
    assert response.json()["version_verified"] is False
    assert learning_state() == before


def test_source_reads_original_version_without_exposing_secrets_or_changing_learning_state(client, monkeypatch):
    register(client)
    source = "def solve(p):\n    return p['start'] + p['increment']\n"
    attempt_id = save_attempt(client, monkeypatch, source)
    with next(app.dependency_overrides[get_db]()) as db:
        attempt = db.get(CodingAttempt, UUID(attempt_id))
        version = db.get(ExerciseVersion, attempt.exercise_version_id)
        version_uuid = str(version.id)
        # Private runner data must never be part of the recovery projection.
        attempt.result = json.dumps({"status": "unavailable", "internal_answer": "answer-secret", "hidden_output": "grader-secret"})
        db.add(ExerciseVersion(
            exercise_id=attempt.exercise_id, version=2,
            content_snapshot={"solution": "new-solution-secret", "hidden_tests": ["hidden-test-secret"]},
        ))
        skill_id = "recovery-sentinel-skill"
        db.add(Skill(id=skill_id, name="Sentinel", category="Python", description="Existing learning state"))
        db.flush()
        db.add(SkillEvidence(
            user_id=attempt.user_id, skill_id=skill_id, source_type="coding_attempt",
            source_id=str(attempt.id), result_score=0.5, occurred_at=datetime.now(timezone.utc),
            idempotency_key="existing-evidence-secret", evidence_metadata={"sentinel": True},
        ))
        db.add(UserSkill(
            user_id=attempt.user_id, skill_id=skill_id, knowledge_score=0.4,
            practice_score=0.5, independent_score=0.3, evidence_count=1,
        ))
        db.commit()
    before = learning_state()
    assert before["execution_jobs"] and before["submission_results"]
    assert before["skill_evidence"] and before["user_skills"]
    monkeypatch.setattr("app.coding_exercises.resolve_coding_exercise", fail_if_called)
    monkeypatch.setattr("app.practice.accessible_lesson", fail_if_called)
    monkeypatch.setattr("app.practice.runner.run", fail_if_called)
    monkeypatch.setattr("app.practice._persist_result_and_evidence", fail_if_called)
    monkeypatch.setattr("app.practice.record_evidence", fail_if_called)
    monkeypatch.setattr("app.jobs_api.enqueue_owned", fail_if_called)
    endpoint = f"/learning/attempts/{attempt_id}/source"
    for _ in range(2):
        response = client.get(endpoint)
        assert response.status_code == 200
        data = response.json()
        assert set(data) == PUBLIC_SOURCE_FIELDS
        assert data["source_code"] == source
        assert data["exercise_version"] == 1 and data["version_verified"] is True
        for secret in (
            version_uuid, "content_snapshot", "internal_answer", "answer-secret",
            "grader-secret", "new-solution-secret", "hidden-test-secret",
            "existing-evidence-secret", "idempotency_key", "request_key_digest",
        ):
            assert secret not in response.text
    assert learning_state() == before
