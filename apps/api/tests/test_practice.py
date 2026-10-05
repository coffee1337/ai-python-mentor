from sqlalchemy import func, select
from app.db.models import CodingAttempt, ExerciseVersion, SubmissionResult
from app.db.session import get_db
from app.main import app
from test_auth import client, csrf

def setup_user(c, email="practice@example.com"):
    from app.auth import _attempts
    _attempts.clear()
    assert c.post("/auth/register", json={"email":email,"password":"safe-password"}).status_code == 201
    assert c.post("/onboarding", headers={"X-CSRF-Token":csrf(c)}, json={"experience_level":"beginner","target_role":"Python Backend","weekly_minutes":180}).status_code == 200

def test_attempt_auth_csrf_and_owned_history(client):
    assert client.post("/learning/exercises/variables-v1/attempts", json={}).status_code == 401
    setup_user(client)
    url="/learning/exercises/variables-v1/attempts"
    body={"language":"python","mode":"function","source_code":"def solve():\n    return 42"}
    assert client.post(url,json=body).status_code == 403
    response=client.post(url,headers={"X-CSRF-Token":csrf(client)},json=body)
    assert response.status_code == 201
    data=response.json(); assert data["status"] == "unavailable" and "не выполнялся" in data["result"]["message"]
    assert client.get(url).json()[0]["id"] == data["id"]
    client.post("/auth/logout",headers={"X-CSRF-Token":csrf(client)})
    setup_user(client,"other@example.com")
    assert client.get(url).json() == []
    with next(app.dependency_overrides[get_db]()) as db:
        row=db.scalar(select(CodingAttempt))
        assert row.user_id is not None and row.source_code == body["source_code"]
        assert db.scalar(select(func.count()).select_from(CodingAttempt)) == 1

def test_attempt_validation_and_unknown_exercise(client):
    setup_user(client)
    url="/learning/exercises/variables-v1/attempts"; headers={"X-CSRF-Token":csrf(client)}
    assert client.post(url,headers=headers,json={"language":"javascript","mode":"function","source_code":"x"}).status_code == 422
    assert client.post(url,headers=headers,json={"language":"python","mode":"script","source_code":"x"}).status_code == 422
    assert client.post(url,headers=headers,json={"language":"python","mode":"function","source_code":"x"*20001}).status_code == 422
    assert client.get("/learning/exercises/missing/attempts").status_code == 404


def test_runner_timeout_and_error_are_normalized(client, monkeypatch):
    setup_user(client, "runner@example.com")
    url="/learning/exercises/variables-v1/attempts"; headers={"X-CSRF-Token":csrf(client)}
    from app.practice import runner
    monkeypatch.setattr(runner, "run", lambda **kwargs: (_ for _ in ()).throw(TimeoutError()))
    timeout=client.post(url, headers=headers, json={"language":"python","mode":"function","source_code":"x"})
    assert timeout.status_code == 201 and timeout.json()["status"] == "timeout"
    monkeypatch.setattr(runner, "run", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("internal")))
    failed=client.post(url, headers=headers, json={"language":"python","mode":"function","source_code":"y"})
    assert failed.status_code == 201 and failed.json()["status"] == "runner_error"


def test_runner_pass_and_wrong_answer_results_are_persisted(client, monkeypatch):
    setup_user(client, "mock-runner@example.com")
    from app.practice import runner
    from app.runner import RunnerResult
    url="/learning/exercises/variables-v1/attempts"; headers={"X-CSRF-Token":csrf(client)}
    monkeypatch.setattr(runner, "run", lambda **kwargs: RunnerResult(status="passed", message="3/3 tests passed", tests_passed=3, tests_total=3))
    ok=client.post(url,headers=headers,json={"language":"python","mode":"function","source_code":"def solve(n): return n+1"})
    assert ok.status_code == 201 and ok.json()["status"] == "passed"
    monkeypatch.setattr(runner, "run", lambda **kwargs: RunnerResult(status="failed", message="1/3 tests passed", tests_passed=1, tests_total=3))
    bad=client.post(url,headers=headers,json={"language":"python","mode":"function","source_code":"def solve(n): return n"})
    assert bad.status_code == 201 and bad.json()["status"] == "failed"

    with next(app.dependency_overrides[get_db]()) as db:
        attempts = db.scalars(select(CodingAttempt).order_by(CodingAttempt.created_at)).all()
        results = db.scalars(select(SubmissionResult).order_by(SubmissionResult.created_at)).all()
        assert len(attempts) == len(results) == 2
        for attempt, result in zip(attempts, results):
            assert attempt.exercise_version_id is not None
            version = db.get(ExerciseVersion, attempt.exercise_version_id)
            assert version is not None
            assert version.exercise_id == attempt.exercise_id
            assert result.coding_attempt_id == attempt.id
            assert result.exercise_version_id == attempt.exercise_version_id
            assert result.idempotency_key == str(attempt.id)
            assert result.protocol_version == 1
            assert result.tests_passed <= result.tests_total

def test_runner_unavailable_configuration_stays_fail_closed(client, monkeypatch):
    setup_user(client, "not-configured@example.com")
    from app.practice import runner
    from app.runner import RunnerUnavailable
    def unavailable(**kwargs): raise RunnerUnavailable("no reviewed worker")
    monkeypatch.setattr(runner, "run", unavailable)
    result=client.post("/learning/exercises/variables-v1/attempts",headers={"X-CSRF-Token":csrf(client)},json={"language":"python","mode":"function","source_code":"print('must not execute')"})
    assert result.status_code == 201 and result.json()["status"] == "unavailable"
    assert "не выполнялся" in result.json()["result"]["message"]
