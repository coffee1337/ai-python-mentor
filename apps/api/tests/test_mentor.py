import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app import ai_gateway
from app.db.models import AIUsageLedger, LessonCompletion
from app.db.session import get_db
from app.main import app
from test_auth import client, csrf
from test_learning import register, onboard, complete

PATH = "/learning/lessons/variables-v1/chat"


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_URL", "https://provider.example/v1/chat/completions")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "test-model")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "secret-test-key")
    calls = []
    state = {"status": 200, "timeout": False, "body": {
        "choices": [{"message": {"role": "assistant", "content": "Что меняет присваивание?"},
                     "finish_reason": "stop"}]}}
    real_client = httpx.Client

    def handler(request):
        calls.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer secret-test-key"
        if state["timeout"]:
            raise httpx.ReadTimeout("secret-test-key", request=request)
        return httpx.Response(state["status"], json=state["body"])

    monkeypatch.setattr(ai_gateway.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    return state, calls


def send(client, request_id=None, message="Помоги понять присваивание"):
    return client.post(PATH, headers={"X-CSRF-Token": csrf(client)},
                       json={"request_id": str(request_id or uuid4()), "message": message})


def ledger_rows():
    with next(app.dependency_overrides[get_db]()) as db:
        return list(db.scalars(select(AIUsageLedger)))


def test_missing_config_and_access(client, monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_URL", raising=False)
    assert client.get(PATH).status_code == 401
    assert send(client).status_code == 401
    register(client)
    assert client.get(PATH).status_code == 409
    onboard(client)
    assert client.get(PATH).json() == []
    assert send(client).status_code == 503
    assert client.post(PATH, json={"request_id": str(uuid4()), "message": "help"}).status_code == 403
    assert send(client, message=" ").status_code == 422
    assert send(client, message="x" * 4001).status_code == 422
    assert client.get("/learning/lessons/conditions-v1/chat").status_code == 409
    assert client.get("/learning/lessons/missing/chat").status_code == 404


def test_missing_config_saved_and_retry_after_configuration(client, provider, monkeypatch):
    register(client); onboard(client)
    request_id = uuid4()
    with monkeypatch.context() as missing_config:
        missing_config.delenv("AI_GATEWAY_URL")
        for _ in range(2):
            assert send(client, request_id).status_code == 503
            history = client.get(PATH).json()
            assert len(history) == 1
            assert history[0]["id"] == str(request_id)
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "Помоги понять присваивание"
            assert history[0]["status"] == "failed"
        assert provider[1] == []

    response = send(client, request_id)
    assert response.status_code == 200
    assert len(provider[1]) == 1
    history = client.get(PATH).json()
    assert [row["role"] for row in history] == ["user", "assistant"]
    assert history[0]["id"] == str(request_id)
    assert all(row["status"] == "completed" for row in history)
    assert send(client, request_id).json()["id"] == response.json()["id"]
    assert len(provider[1]) == 1
    assert len(client.get(PATH).json()) == 2


def test_success_history_retry_and_evidence(client, provider):
    register(client); onboard(client)
    request_id = uuid4()
    first = send(client, request_id)
    assert first.status_code == 200
    assert send(client, request_id).json()["id"] == first.json()["id"]
    assert len(provider[1]) == 1
    assert send(client, request_id, "different").status_code == 409
    history = client.get(PATH).json()
    assert [row["role"] for row in history] == ["user", "assistant"]
    request = provider[1][0]
    assert request["model"] == "test-model"
    assert "beginner" in request["messages"][1]["content"]
    assert '"answer"' not in request["messages"][1]["content"]
    assert request["messages"][-1]["content"] == "Помоги понять присваивание"
    assert complete(client).status_code == 200
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(LessonCompletion)).evidence_type == "authored_quiz_assisted"


def test_success_records_usage_with_safe_token_types_and_character_counts(client, provider):
    register(client); onboard(client)
    provider[0]["body"]["usage"] = {
        "prompt_tokens": 17,
        "completion_tokens": "not-an-int",
    }

    response = send(client)

    assert response.status_code == 200
    row = ledger_rows()[0]
    request = provider[1][0]
    assert row.operation == "mentor_chat"
    assert row.model_id == "test-model"
    assert row.generation_id is None
    assert row.cache_hit is False
    assert row.status == "completed"
    assert row.input_chars == sum(len(message["content"]) for message in request["messages"])
    assert row.output_chars == len(response.json()["content"])
    assert row.input_tokens == 17
    assert row.output_tokens is None


def test_gateway_error_records_usage_without_provider_details(client, provider):
    register(client); onboard(client)
    state, calls = provider
    state["status"] = 500
    state["body"] = {"error": "secret-test-key"}

    response = send(client)

    assert response.status_code == 502
    assert "secret-test-key" not in response.text
    row = ledger_rows()[0]
    assert row.operation == "mentor_chat"
    assert row.model_id == "test-model"
    assert row.generation_id is None
    assert row.cache_hit is False
    assert row.status == "gateway_error"
    assert row.input_chars == sum(len(message["content"]) for message in calls[0]["messages"])
    assert row.output_chars == 0
    assert row.input_tokens is None
    assert row.output_tokens is None


def test_repeated_request_id_records_a_cache_hit_without_another_provider_call(client, provider):
    register(client); onboard(client)
    request_id = uuid4()

    first = send(client, request_id)
    second = send(client, request_id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert len(provider[1]) == 1
    rows = ledger_rows()
    assert len(rows) == 2
    assert {row.cache_hit for row in rows} == {False, True}
    cached = next(row for row in rows if row.cache_hit)
    assert cached.status == "cache_hit"
    assert cached.input_chars == len("Помоги понять присваивание")
    assert cached.output_chars == len(first.json()["content"])


@pytest.mark.parametrize("failure,expected", [("timeout", 504), ("http", 502), ("schema", 502)])
def test_failure_saved_and_explicit_retry(client, provider, failure, expected):
    register(client); onboard(client)
    state, calls = provider
    good_body = state["body"]
    if failure == "timeout":
        state["timeout"] = True
    elif failure == "http":
        state["status"] = 500
        state["body"] = {"error": "secret-test-key"}
    else:
        state["body"] = {"choices": []}
    request_id = uuid4()
    response = send(client, request_id)
    assert response.status_code == expected
    assert "secret-test-key" not in response.text
    assert len(calls) == 1
    assert client.get(PATH).json()[0]["status"] == "failed"
    state.update(timeout=False, status=200, body=good_body)
    assert send(client, request_id).status_code == 200
    assert len(calls) == 2
    assert len(client.get(PATH).json()) == 2


def test_ownership_and_rate_limit(client, provider):
    register(client); onboard(client)
    request_id = uuid4()
    assert send(client, request_id).status_code == 200
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    register(client, "other@example.com"); onboard(client)
    assert client.get(PATH).json() == []
    assert send(client, request_id).status_code == 404
    for _ in range(5):
        assert send(client).status_code == 200
    assert send(client).status_code == 429
    assert len(provider[1]) == 6
