"""Prompt 07 runner protocol tests: mock worker, timeout/unavailable, evidence/hints, public/hidden.

No user code is executed here; the worker is always mocked or fail-closed.
Only tests and minimal fixtures live in this file.
"""
import pytest
from sqlalchemy import select

from app.db.models import (
    CodingAttempt,
    ExerciseVersion,
    KnowledgeCheckAttempt,
    MentorConversation,
    MentorMessage,
    SubmissionResult,
    SkillEvidence,
    User,
)
from app.db.session import get_db
from app.main import app
from app.runner import Runner, RunnerResult, RunnerUnavailable
from app.skill_evidence import derive_assistance, record_evidence
from test_auth import client, csrf


def setup_user(c, email):
    from app.auth import _attempts
    _attempts.clear()
    assert c.post("/auth/register", json={"email": email, "password": "safe-password"}).status_code == 201
    assert c.post(
        "/onboarding",
        headers={"X-CSRF-Token": csrf(c)},
        json={"experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180},
    ).status_code == 200


def submit_attempt(c, source_code="def solve():\n    return 42"):
    return c.post(
        "/learning/exercises/variables-v1/attempts",
        headers={"X-CSRF-Token": csrf(c)},
        json={"language": "python", "mode": "function", "source_code": source_code},
    )


def correct_check_answers(c):
    from app.knowledge_check_content import CHECKS
    questions = c.get("/learning/lessons/variables-v1/knowledge-check").json()
    authored = {q["id"]: q["answer"] for q in CHECKS["variables-v1"]}
    return {q["id"]: authored[q["id"]] for q in questions}


def test_worker_result_contract_is_normalized_and_persisted(client, monkeypatch):
    setup_user(client, "p07-contract@example.com")
    from app.practice import runner
    seen = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return RunnerResult(
            status="failed",
            message="7/10 tests passed",
            exit_code=0,
            tests_passed=7,
            tests_total=10,
            timeout=False,
            resource_violation=False,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(runner, "run", fake_run)
    resp = submit_attempt(client, "def solve():\n    return 1")
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "failed"
    result = data["result"]
    assert result["tests_passed"] == 7
    assert result["tests_total"] == 10
    assert result["timeout"] is False
    assert result["resource_violation"] is False
    assert result["stdout"] == "ok"
    assert result["stderr"] == ""
    # Client controls only code+mode; it cannot inject tests, commands, or images.
    assert set(seen.keys()) == {"exercise_id", "source_code", "language", "mode"}
    assert seen["exercise_id"] == "variables-v1"
    assert seen["language"] == "python"
    assert seen["mode"] == "function"
    # Normalized result never echoes source code or hidden test source.
    assert "source_code" not in data
    assert "source_code" not in result
    for forbidden in ("hidden_tests", "test_source", "test_code", "hidden"):
        assert forbidden not in result
    history = client.get("/learning/exercises/variables-v1/attempts").json()
    assert history[0]["id"] == data["id"]
    assert "source_code" not in history[0]
    with next(app.dependency_overrides[get_db]()) as db:
        row = db.scalar(select(CodingAttempt))
        assert row is not None
        assert row.status == "failed"
        assert row.source_code == "def solve():\n    return 1"
        evidence = db.scalar(select(SkillEvidence))
        assert evidence is not None
        assert evidence.source_type == "coding_attempt"
        assert evidence.skill_id == "python.variables"
        assert evidence.result_score == 0.7
        assert evidence.assisted is False
        assert evidence.hint_count == 0


def test_worker_timeout_is_normalized_without_evidence(client, monkeypatch):
    setup_user(client, "p07-timeout@example.com")
    from app.practice import runner

    def raise_timeout(**kwargs):
        raise TimeoutError()

    monkeypatch.setattr(runner, "run", raise_timeout)
    resp = submit_attempt(client, "def solve():\n    while True: pass")
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "timeout"
    assert data["result"]["timeout"] is True
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(CodingAttempt)).status == "timeout"
        assert db.scalars(select(SkillEvidence)).all() == []


def test_unavailable_runner_is_fail_closed_and_never_executes(client, monkeypatch):
    setup_user(client, "p07-unavailable@example.com")
    # Fresh boundary instance never executes in the API process.
    with pytest.raises(RunnerUnavailable):
        Runner().run(
            exercise_id="variables-v1",
            source_code="print('must not execute')",
            language="python",
            mode="function",
        )
    from app.practice import runner
    calls = []

    def fake_unavailable(**kwargs):
        calls.append(kwargs)
        raise RunnerUnavailable("no reviewed worker")

    monkeypatch.setattr(runner, "run", fake_unavailable)
    payload = "__import__('os').system('echo pwned')"
    resp = submit_attempt(client, payload)
    assert resp.status_code == 201
    assert resp.json()["status"] == "unavailable"
    assert calls and calls[0]["source_code"] == payload
    with next(app.dependency_overrides[get_db]()) as db:
        row = db.scalar(select(CodingAttempt))
        assert row.status == "unavailable"
        assert row.source_code == payload
        assert db.scalars(select(SkillEvidence)).all() == []


def test_coding_result_becomes_server_attributed_evidence(client, monkeypatch):
    setup_user(client, "p07-coding-evidence@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    for level in (1, 2):
        reveal = client.post(
            "/learning/exercises/variables-v1/hints",
            headers={**headers, "Idempotency-Key": f"p07-code-hint-{level}"},
            json={"level": level},
        )
        assert reveal.status_code == 200
    from app.practice import runner
    monkeypatch.setattr(
        runner,
        "run",
        lambda **kwargs: RunnerResult(status="passed", message="ok", tests_passed=3, tests_total=3),
    )
    resp = submit_attempt(client, "def solve():\n    return 1")
    assert resp.status_code == 201
    assert resp.json()["status"] == "passed"
    with next(app.dependency_overrides[get_db]()) as db:
        from app.db.models import User
        user = db.scalar(select(User))
        attempt = db.scalar(select(CodingAttempt))
        assert attempt is not None
        assert derive_assistance(
            db, user_id=user.id, source_type="coding_attempt", source_id=str(attempt.id)
        ) == (True, 2)
        evidence = db.scalar(select(SkillEvidence))
        assert evidence is not None
        assert evidence.source_type == "coding_attempt"
        assert evidence.source_id == str(attempt.id)
        assert evidence.skill_id == "python.variables"
        assert evidence.result_score == 1.0
        assert evidence.assisted is True
        assert evidence.hint_count == 2
        # Replaying through the public domain entry point is idempotent. The
        # caller cannot overwrite server-derived assistance.
        replay = record_evidence(
            db,
            user_id=user.id,
            skill_id=None,
            source_type="coding_attempt",
            source_id=str(attempt.id),
            result_score=None,
            assisted=False,
            hint_count=0,
        )
        assert replay.id == evidence.id
        assert db.scalars(select(SkillEvidence)).all() == [evidence]
        with pytest.raises(ValueError, match="skill"):
            record_evidence(
                db,
                user_id=user.id,
                skill_id="python.conditionals",
                source_type="coding_attempt",
                source_id=str(attempt.id),
                result_score=None,
            )
        with pytest.raises(ValueError, match="score"):
            record_evidence(
                db,
                user_id=user.id,
                skill_id=None,
                source_type="coding_attempt",
                source_id=str(attempt.id),
                result_score=0.5,
            )


def test_coding_evidence_requires_attempt_ownership(client, monkeypatch):
    setup_user(client, "p07-owner@example.com")
    from app.practice import runner

    monkeypatch.setattr(
        runner,
        "run",
        lambda **kwargs: RunnerResult(status="passed", message="ok", tests_passed=1, tests_total=1),
    )
    resp = submit_attempt(client)
    assert resp.status_code == 201

    with next(app.dependency_overrides[get_db]()) as db:
        owner = db.scalar(select(User).where(User.email == "p07-owner@example.com"))
        attempt = db.scalar(select(CodingAttempt))
        other = User(email="p07-other@example.com", password_hash="not-used")
        db.add(other)
        db.commit()
        with pytest.raises(ValueError, match="owned"):
            record_evidence(
                db,
                user_id=other.id,
                skill_id=None,
                source_type="coding_attempt",
                source_id=str(attempt.id),
                result_score=None,
            )
        evidence = db.scalar(select(SkillEvidence))
        assert evidence is not None and evidence.user_id == owner.id


def test_hints_revealed_after_result_are_not_attributed(client, monkeypatch):
    setup_user(client, "p07-late-hint@example.com")
    from app.practice import runner

    monkeypatch.setattr(
        runner,
        "run",
        lambda **kwargs: RunnerResult(status="passed", message="ok", tests_passed=2, tests_total=2),
    )
    resp = submit_attempt(client)
    assert resp.status_code == 201

    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(CodingAttempt)).user_id
        evidence = db.scalar(select(SkillEvidence))
        assert evidence is not None
        assert evidence.assisted is False
        assert evidence.hint_count == 0

    reveal = client.post(
        "/learning/exercises/variables-v1/hints",
        headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "p07-late-hint"},
        json={"level": 1},
    )
    assert reveal.status_code == 200

    with next(app.dependency_overrides[get_db]()) as db:
        attempt = db.scalar(select(CodingAttempt))
        assert derive_assistance(
            db, user_id=user, source_type="coding_attempt", source_id=str(attempt.id)
        ) == (False, 0)
        evidence = db.scalar(select(SkillEvidence))
        assert evidence.assisted is False
        assert evidence.hint_count == 0


def test_resource_violation_has_no_coding_evidence(client, monkeypatch):
    setup_user(client, "p07-resource@example.com")
    from app.practice import runner

    monkeypatch.setattr(
        runner,
        "run",
        lambda **kwargs: RunnerResult(
            status="resource_violation",
            message="limit",
            tests_passed=0,
            tests_total=0,
            resource_violation=True,
        ),
    )
    resp = submit_attempt(client)
    assert resp.status_code == 201
    assert resp.json()["status"] == "resource_violation"
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalars(select(SkillEvidence)).all() == []


def test_malformed_terminal_result_is_fail_closed(client, monkeypatch):
    setup_user(client, "p07-malformed-result@example.com")
    from app.practice import runner

    monkeypatch.setattr(
        runner,
        "run",
        lambda **kwargs: RunnerResult(
            status="passed",
            message="invalid",
            tests_passed=2,
            tests_total=1,
        ),
    )
    resp = submit_attempt(client)
    assert resp.status_code == 201
    assert resp.json()["status"] == "runner_error"
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalars(select(SkillEvidence)).all() == []
        result = db.scalar(select(SubmissionResult))
        assert result is not None and result.status == "runner_error"


def test_invalid_snapshot_keeps_result_but_writes_no_partial_evidence(client):
    setup_user(client, "p07-invalid-snapshot@example.com")
    assert client.get("/learning/lessons/variables-v1").status_code == 200
    from app.practice import _persist_result_and_evidence

    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        version = db.scalar(
            select(ExerciseVersion).where(ExerciseVersion.exercise_id == "variables-v1")
        )
        assert user is not None and version is not None
        version.content_snapshot = None
        attempt = CodingAttempt(
            user_id=user.id,
            exercise_id="variables-v1",
            exercise_version_id=version.id,
            language="python",
            mode="function",
            source_code="unexecuted",
            status="unavailable",
            result="{}",
        )
        db.add(attempt)
        db.flush()

        _persist_result_and_evidence(
            db,
            attempt,
            RunnerResult(status="passed", message="ok", tests_passed=1, tests_total=1),
        )

        stored = db.scalar(
            select(SubmissionResult).where(SubmissionResult.coding_attempt_id == attempt.id)
        )
        assert stored is not None
        assert stored.skill_evidence_id is None
        assert db.scalars(select(SkillEvidence)).all() == []


def test_mentor_chat_without_hint_reveal_is_not_hint_attribution(client):
    setup_user(client, "p07-mentor-hint@example.com")
    answers = correct_check_answers(client)
    resp = client.post(
        "/learning/lessons/variables-v1/knowledge-check",
        headers={"X-CSRF-Token": csrf(client)},
        json={"answers": answers},
    )
    assert resp.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        from app.db.models import User
        user = db.scalar(select(User))
        attempt = db.scalar(select(KnowledgeCheckAttempt))
        assert attempt is not None
        conv = MentorConversation(user_id=user.id, lesson_id="variables-v1")
        db.add(conv)
        db.flush()
        db.add(MentorMessage(conversation_id=conv.id, role="user", content="give me the answer", status="completed"))
        db.add(MentorMessage(conversation_id=conv.id, role="assistant", content="try counting", status="completed"))
        db.flush()
        assert derive_assistance(
            db, user_id=user.id, source_type="knowledge_check_attempt", source_id=str(attempt.id)
        ) == (False, 0)
        evidence = db.scalar(select(SkillEvidence))
        assert evidence is not None
        assert evidence.assisted is False
        assert evidence.hint_count == 0


def test_public_hidden_results_expose_counts_not_sources(client, monkeypatch):
    setup_user(client, "p07-hidden@example.com")
    from app.practice import runner
    monkeypatch.setattr(
        runner,
        "run",
        lambda **kwargs: RunnerResult(
            status="failed",
            message="public 2/2, hidden 5/8",
            exit_code=1,
            tests_passed=5,
            tests_total=8,
            timeout=False,
            resource_violation=False,
            stdout="public ok",
            stderr="",
        ),
    )
    resp = submit_attempt(client, "def solve(n):\n    return n")
    assert resp.status_code == 201
    result = resp.json()["result"]
    assert result["status"] == "failed"
    assert result["tests_passed"] == 5
    assert result["tests_total"] == 8
    blob = resp.text + client.get("/learning/lessons/variables-v1/knowledge-check").text
    for forbidden in ("hidden_tests", "test_source", "def test_", "assert solve"):
        assert forbidden not in blob
