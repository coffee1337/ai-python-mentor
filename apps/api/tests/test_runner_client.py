import json

import httpx
import pytest

from app.practice import runner as api_runner
from app.runner import Runner, RunnerError, RunnerUnavailable
from test_auth import client, csrf


KEY = "2bf5e3d2-13e2-4a1d-8c32-4ed646e2c0f9"
TOKEN = "runner-test-secret"
SOURCE = "def solve(value):\n    return value + 1\n"


def configure(monkeypatch):
    monkeypatch.setenv("RUNNER_URL", "https://runner.internal")
    monkeypatch.setenv("RUNNER_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("RUNNER_REQUEST_TIMEOUT_SECONDS", "3")


def wire_response(key=KEY, **overrides):
    payload = {
        "protocol_version": 1,
        "idempotency_key": key,
        "status": "finished",
        "tests_passed": 3,
        "tests_total": 3,
        "timeout": False,
        "resource_violation": False,
        "stdout": "ok\n",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "exit_code": 0,
        "error_code": None,
        "message": "worker-controlled details must not be echoed",
    }
    payload.update(overrides)
    return payload


def submit(transport):
    return Runner(transport=transport).run(
        exercise_id="variables-v1",
        exercise_version=3,
        source_code=SOURCE,
        language="python",
        mode="function",
        idempotency_key=KEY,
    )




def test_practice_passes_pinned_version_and_attempt_idempotency_key(client, monkeypatch):
    assert client.post(
        "/auth/register",
        json={"email": "runner-client@example.com", "password": "safe-password"},
    ).status_code == 201
    assert client.post(
        "/onboarding",
        headers={"X-CSRF-Token": csrf(client)},
        json={"experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180},
    ).status_code == 200
    configure(monkeypatch)
    seen = {}

    def handler(request):
        seen["key"] = request.headers["Idempotency-Key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=wire_response(key=seen["key"]))

    monkeypatch.setattr(api_runner, "_transport", httpx.MockTransport(handler))
    response = client.post(
        "/learning/exercises/variables-v1/attempts",
        headers={"X-CSRF-Token": csrf(client)},
        json={"language": "python", "mode": "function", "source_code": SOURCE},
    )

    assert response.status_code == 201
    assert seen["key"] == response.json()["id"]
    assert seen["body"]["exercise_version"] == 1
    assert seen["body"]["source"] == SOURCE
    assert response.json()["status"] == "passed"

def test_request_uses_exact_private_contract_and_stable_idempotency_header(monkeypatch):
    configure(monkeypatch)
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("Idempotency-Key")
        seen["authorization"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=wire_response())

    result = submit(httpx.MockTransport(handler))

    assert seen["url"] == "https://runner.internal/internal/v1/runner/executions"
    assert seen["key"] == KEY
    assert seen["authorization"] == f"Bearer {TOKEN}"
    assert seen["body"] == {
        "protocol_version": 1,
        "exercise_id": "variables-v1",
        "exercise_version": 3,
        "language": "python",
        "source": SOURCE,
        "mode": "function",
    }
    assert "command" not in seen["body"] and "path" not in seen["body"]
    assert result.status == "passed"
    assert result.tests_passed == result.tests_total == 3
    assert result.message == "3/3 tests passed"


def test_worker_timeout_is_a_terminal_timeout_result(monkeypatch):
    configure(monkeypatch)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=wire_response(
                status="timeout",
                tests_passed=0,
                tests_total=3,
                timeout=True,
                message="private timeout detail",
            ),
        )
    )
    result = submit(transport)
    assert result.status == "timeout"
    assert result.timeout is True
    assert result.message == "Runner timed out"


def test_partial_finished_result_is_failed_not_success(monkeypatch):
    configure(monkeypatch)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=wire_response(tests_passed=1, tests_total=3))
    )
    result = submit(transport)
    assert result.status == "failed"
    assert result.message == "1/3 tests passed"


def test_missing_configuration_fails_closed_without_network(monkeypatch):
    for name in ("RUNNER_URL", "RUNNER_AUTH_TOKEN", "RUNNER_REQUEST_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RunnerUnavailable):
        Runner().run(
            exercise_id="variables-v1",
            exercise_version=1,
            source_code=SOURCE,
            language="python",
            mode="function",
            idempotency_key=KEY,
        )


def test_transport_timeout_is_unavailable_not_execution_timeout(monkeypatch):
    configure(monkeypatch)

    def handler(_request):
        raise httpx.ReadTimeout("transport details")

    with pytest.raises(RunnerUnavailable) as exc:
        submit(httpx.MockTransport(handler))
    assert "transport details" not in str(exc.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"extra_field": "not allowed"},
        {"protocol_version": 2},
        {"idempotency_key": "some-other-attempt"},
        {"tests_passed": True},
        {"tests_passed": 4},
        {"status": "timeout", "timeout": False},
        {"status": "finished", "tests_passed": 0, "tests_total": 0},
    ],
)
def test_protocol_errors_fail_closed(monkeypatch, overrides):
    configure(monkeypatch)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=wire_response(**overrides))
    )
    with pytest.raises(RunnerUnavailable):
        submit(transport)


def test_worker_error_is_normalized_without_exposing_worker_message(monkeypatch):
    configure(monkeypatch)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=wire_response(status="error", message="private worker detail"))
    )
    result = submit(transport)
    assert result.status == "error"
    assert result.message == "Runner failed"
    assert "private worker detail" not in result.message


def test_error_response_body_is_validated_but_never_exposed(monkeypatch):
    configure(monkeypatch)
    response = wire_response(
        status="unavailable",
        tests_passed=0,
        tests_total=0,
        stdout="",
        stderr="",
        exit_code=None,
        error_code="worker_not_ready",
        message="worker not ready",
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(503, json=response))
    result = submit(transport)
    assert result.status == "unavailable"
    assert result.error_code == "worker_not_ready"
    assert TOKEN not in result.message


def test_request_validation_rejects_oversized_source_before_dispatch(monkeypatch):
    configure(monkeypatch)
    called = False

    def handler(_request):
        nonlocal called
        called = True
        return httpx.Response(200, json=wire_response())

    with pytest.raises(RunnerError):
        Runner(transport=httpx.MockTransport(handler)).run(
            exercise_id="variables-v1",
            exercise_version=1,
            source_code="é" * 20001,
            language="python",
            mode="function",
            idempotency_key=KEY,
        )
    assert not called
