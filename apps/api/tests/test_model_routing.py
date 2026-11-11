"""Routing, retry/fallback and global spend accounting for the AI gateway."""
import contextlib
import json
import logging
import time
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from test_auth import client
from test_learning import onboard, register

from app import ai_admission, ai_gateway, model_catalog
from app.ai_admission import reserve_ai_call
from app.ai_gateway import GatewayError
from app.db.domain_models import AICallReservation
from app.db.models import User
from app.db.session import get_db
from app.main import app

CATALOG = {
    "version": 1,
    "provider": {"name": "test", "checked_at": "2026-11-10T00:00:00Z"},
    "models": {
        "cheap-a": {"input_micro_usd_per_million": 100000, "output_micro_usd_per_million": 100000, "multiplier": 0.1},
        "cheap-b": {"input_micro_usd_per_million": 300000, "output_micro_usd_per_million": 300000, "multiplier": 0.3},
        "strong-a": {"input_micro_usd_per_million": 2000000, "output_micro_usd_per_million": 2000000, "multiplier": 2},
    },
    "tiers": {"fast": ["cheap-a", "cheap-b"], "strong": ["strong-a"]},
    "tasks": {task: ("fast" if task in {"tutor_chat", "hint_ladder", "error_explanation", "answer_feedback"}
                     else "strong") for task in model_catalog.TASKS},
    "default_task": "tutor_chat",
}


def write_catalog(tmp_path, document=None):
    path = tmp_path / "routing.json"
    path.write_text(json.dumps(document or CATALOG), encoding="utf-8")
    return path


@pytest.fixture
def routed(monkeypatch, tmp_path):
    path = write_catalog(tmp_path)
    monkeypatch.setenv("AI_MODEL_ROUTING_FILE", str(path))
    monkeypatch.setenv("AI_GATEWAY_URL", "https://provider.example/v1/chat/completions")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "secret-test-key")
    monkeypatch.delenv("AI_GATEWAY_MODEL", raising=False)
    monkeypatch.setenv("AI_RETRY_BASE_SECONDS", "0")
    return path


class _Records(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@contextlib.contextmanager
def captured(name="ai.usage"):
    """Capture this logger's records directly, independent of root handlers."""
    logger = logging.getLogger(name)
    handler = _Records()
    previous_level, previous_disabled = logger.level, logger.disabled
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.disabled = False
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.disabled = previous_disabled


def fake_client(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(ai_gateway.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def answer(model, text="ok"):
    return {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20}}


def test_catalog_is_validated_and_tiers_are_ordered(routed):
    catalog = model_catalog.load(routed)
    assert catalog.chain("tutor_chat") == ("cheap-a", "cheap-b")
    assert catalog.chain("lesson_generation") == ("strong-a",)
    assert catalog.price("cheap-a").micro_usd(1000, 1000) == 200
    with pytest.raises(model_catalog.RoutingError):
        catalog.chain("does-not-exist")


def test_catalog_rejects_tier_with_unpriced_model(tmp_path):
    broken = json.loads(json.dumps(CATALOG))
    broken["tiers"]["fast"] = ["cheap-a", "ghost-model"]
    with pytest.raises(model_catalog.RoutingError):
        model_catalog.parse(broken)


def test_catalog_rejects_missing_task_mapping(tmp_path):
    broken = json.loads(json.dumps(CATALOG))
    broken["tasks"].pop("code_review")
    with pytest.raises(model_catalog.RoutingError):
        model_catalog.parse(broken)


def test_configuration_uses_the_task_tier(routed):
    assert ai_gateway.configuration(task="tutor_chat").models == ("cheap-a", "cheap-b")
    assert ai_gateway.configuration(task="code_review").models == ("strong-a",)
    assert ai_gateway.configuration().models == ("cheap-a", "cheap-b")
    assert ai_gateway.configuration(model_override="pinned").models == ("pinned",)


def test_rate_limited_model_falls_back_to_the_next_and_reports_cost(routed, monkeypatch):
    seen = []

    def handler(request):
        model = json.loads(request.content)["model"]
        seen.append(model)
        if model == "cheap-a":
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json=answer(model))

    fake_client(monkeypatch, handler)
    content, usage = ai_gateway.generate_with_usage(ai_gateway.configuration(task="tutor_chat"),
                                                    [{"role": "user", "content": "hi"}])
    assert content == "ok"
    assert seen == ["cheap-a", "cheap-a", "cheap-b"]
    assert usage["model"] == "cheap-b"
    assert usage["attempts"] == 3
    assert usage["micro_usd"] == 36  # 100 * 0.3 + 20 * 0.3 micro-USD per million tokens


def test_client_error_is_not_retried_and_never_leaks_the_provider_body(routed, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"error": "secret-test-key is invalid"})

    fake_client(monkeypatch, handler)
    with pytest.raises(GatewayError) as exc:
        ai_gateway.generate_with_usage(ai_gateway.configuration(task="tutor_chat"),
                                       [{"role": "user", "content": "hi"}])
    assert exc.value.status == 502
    assert "secret-test-key" not in exc.value.detail
    assert len(calls) == 2  # one attempt per model, no retry on 4xx


def test_timeouts_exhaust_the_chain_and_return_504(routed, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    fake_client(monkeypatch, handler)
    with pytest.raises(GatewayError) as exc:
        ai_gateway.generate_with_usage(ai_gateway.configuration(task="tutor_chat"),
                                       [{"role": "user", "content": "hi"}])
    assert exc.value.status == 504


def test_every_call_is_logged_with_tokens_and_cost(routed, monkeypatch):
    fake_client(monkeypatch, lambda request: httpx.Response(200, json=answer("cheap-a")))
    with captured() as messages:
        ai_gateway.generate_with_usage(ai_gateway.configuration(task="tutor_chat"),
                                       [{"role": "user", "content": "hi"}])
    records = [json.loads(r.message) for r in messages if r.message.startswith("{")]
    call = next(r for r in records if r["event"] == "ai_call")
    assert call["model"] == "cheap-a"
    assert call["prompt_tokens"] == 100 and call["completion_tokens"] == 20
    assert call["micro_usd"] == 12
    assert "hi" not in json.dumps(call)


def test_warmup_issues_one_short_call(routed, monkeypatch):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=answer("cheap-a", "pong"))

    fake_client(monkeypatch, handler)
    assert ai_gateway.warmup() is True
    assert len(seen) == 1
    assert seen[0]["max_completion_tokens"] == 8


def test_total_budget_stops_the_chain(routed, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        time.sleep(0.9)
        raise httpx.ReadTimeout("slow", request=request)

    fake_client(monkeypatch, handler)
    monkeypatch.setattr(ai_gateway, "_total_budget", lambda: 2.0)
    started = time.monotonic()
    with pytest.raises(GatewayError) as exc:
        ai_gateway.generate_with_usage(ai_gateway.configuration(task="tutor_chat"),
                                       [{"role": "user", "content": "hi"}])
    assert exc.value.status == 504
    assert time.monotonic() - started < 4
    assert 1 <= len(requests) <= 3


def session():
    return next(app.dependency_overrides[get_db]())


def learner(client):
    register(client)
    onboard(client)
    with session() as db:
        return db.scalar(select(User.id))


def test_global_daily_limit_blocks_the_next_reservation(client, monkeypatch):
    user_id = learner(client)
    monkeypatch.setenv("AI_SPEND_DAILY_LIMIT_USD", "0.0001")
    monkeypatch.setenv("AI_MAX_CALL_COST_MICROUSD", "50")
    with session() as db:
        reserve_ai_call(db, user_id, "mentor_chat", str(uuid4()), limit=10, window_seconds=3600, input_chars=10)
    with session() as db, pytest.raises(GatewayError) as exc:
        reserve_ai_call(db, user_id, "mentor_chat", str(uuid4()), limit=10, window_seconds=3600, input_chars=10)
    assert exc.value.status == 429
    with session() as db:
        assert db.query(AICallReservation).count() == 1


def test_eighty_percent_threshold_emits_one_alert_per_day(client, monkeypatch):
    user_id = learner(client)
    ai_admission._spend_alerts.clear()
    monkeypatch.setenv("AI_SPEND_DAILY_LIMIT_USD", "0.001")
    monkeypatch.setenv("AI_MAX_CALL_COST_MICROUSD", "850")
    with captured() as messages, session() as db:
        reserve_ai_call(db, user_id, "mentor_chat", str(uuid4()), limit=10, window_seconds=3600, input_chars=10)
    alerts = [json.loads(r.message) for r in messages if r.message.startswith("{")]
    assert len([a for a in alerts if a["event"] == "ai_spend_alert"]) == 1
