"""Metrics endpoint and error-reporting scrubbing."""
import os

from test_auth import client

from app import metrics, observability


def test_metrics_endpoint_exposes_bounded_series(client):
    register = client.post("/auth/register", json={
        "email": "metrics@example.invalid", "password": "Metrics-Password-2026!"})
    assert register.status_code in {200, 201, 409}
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "apm_http_requests_total" in body
    assert "apm_db_up 1.0" in body
    assert "apm_execution_queue_depth" in body


def test_route_labels_use_templates_not_raw_ids(client):
    metrics.REQUESTS.clear()
    client.get("/learning/lessons/variables-v1")
    body = client.get("/metrics").text
    assert "variables-v1" not in body
    assert 'route="unmatched"' in body or 'route="/learning/lessons/{lesson_id}"' in body


def test_ai_observation_counts_tokens_and_cost():
    metrics.AI_CALLS.clear()
    metrics.AI_TOKENS.clear()
    metrics.AI_SPEND.clear()
    metrics.observe_ai("tutor_chat", "gpt-6-luna", "ok",
                       {"prompt_tokens": 100, "completion_tokens": 20, "micro_usd": 36})
    body = metrics.render()[0].decode()
    assert 'apm_ai_calls_total{model="gpt-6-luna",status="ok",task="tutor_chat"} 1.0' in body
    assert 'apm_ai_tokens_total{direction="input",model="gpt-6-luna"} 100.0' in body
    assert 'apm_ai_spend_micro_usd_total{model="gpt-6-luna",task="tutor_chat"} 36.0' in body


def test_quota_and_execution_counters():
    metrics.QUOTA_REJECTIONS.clear()
    metrics.EXECUTIONS.clear()
    metrics.observe_quota("daily_budget")
    metrics.observe_execution("timeout")
    body = metrics.render()[0].decode()
    assert 'apm_quota_rejections_total{reason="daily_budget"} 1.0' in body
    assert 'apm_runner_executions_total{status="timeout"} 1.0' in body


def test_sentry_is_optional(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert observability.init_sentry() is False


def test_sentry_scrubbing_removes_content_headers_and_identity():
    event = {
        "request": {
            "data": '{"source": "def solve(p): return 1"}',
            "query_string": "token=abc",
            "headers": {"Authorization": "Bearer secret", "Cookie": "session=1", "Accept": "text/html"},
        },
        "user": {"id": "0000", "email": "learner@example.invalid"},
    }
    cleaned = observability._scrub(event, {})
    assert "data" not in cleaned["request"] and "query_string" not in cleaned["request"]
    assert cleaned["request"]["headers"]["Authorization"] == "[redacted]"
    assert cleaned["request"]["headers"]["Cookie"] == "[redacted]"
    assert cleaned["request"]["headers"]["Accept"] == "text/html"
    assert "user" not in cleaned
    assert os.environ.get("SENTRY_DSN") is None
