"""Admission behavior survives request/session boundaries and failed calls."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.ai_admission import finish_ai_call, reserve_ai_call
from app.ai_gateway import GatewayError
from app.db.domain_models import AICallReservation, AIRequestLease
from app.db.models import User
from app.db.session import get_db
from app.main import app
from test_auth import client
from test_learning import register, onboard


def session():
    return next(app.dependency_overrides[get_db]())


def learner(client):
    register(client)
    onboard(client)
    with session() as db:
        return db.scalar(select(User.id))


def reserve(db, user_id, key=None, **kwargs):
    return reserve_ai_call(db, user_id, "curriculum_generation", key or str(uuid4()),
                           limit=6, window_seconds=3600, input_chars=20, **kwargs)


def test_hourly_limit_allows_six_calls_and_counts_failures_across_sessions(client):
    user_id = learner(client)
    for index in range(6):
        with session() as db:
            call = reserve(db, user_id)
            finish_ai_call(db, call, status="gateway_error" if index % 2 else "ready")
            db.commit()
    with session() as db:
        with pytest.raises(GatewayError) as exc:
            reserve(db, user_id)
        assert exc.value.status == 429
        assert db.scalar(select(func.count(AICallReservation.id))) == 6


def test_pending_lease_blocks_duplicate_and_expired_worker_cannot_publish(client):
    user_id = learner(client)
    with session() as db:
        first = reserve(db, user_id, "same-input")
        first_id = first.id
    with session() as db:
        with pytest.raises(GatewayError) as exc:
            reserve(db, user_id, "same-input")
        assert exc.value.status == 409
        lease = db.get(AIRequestLease, (user_id, "curriculum_generation", "same-input"))
        lease.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    with session() as db:
        replacement = reserve(db, user_id, "same-input")
        replacement_id = replacement.id
    with session() as db:
        old = db.get(AICallReservation, first_id)
        with pytest.raises(GatewayError) as exc:
            finish_ai_call(db, old, status="ready")
        assert exc.value.status == 409
        db.rollback()
    with session() as db:
        finish_ai_call(db, db.get(AICallReservation, replacement_id), status="ready")
        db.commit()
        assert db.get(AIRequestLease, (user_id, "curriculum_generation", "same-input")).status == "completed"


def test_daily_shared_budget_reserves_pending_calls_and_requires_configuration(client, monkeypatch):
    user_id = learner(client)
    monkeypatch.setenv("AI_DAILY_BUDGET_MICROUSD", "100")
    with session() as db:
        with pytest.raises(GatewayError) as exc:
            reserve(db, user_id)
        assert exc.value.status == 503
    monkeypatch.setenv("AI_MAX_CALL_COST_MICROUSD", "60")
    with session() as db:
        reserve(db, user_id)
    with session() as db:
        with pytest.raises(GatewayError) as exc:
            reserve_ai_call(db, user_id, "mentor_chat", "another-operation", limit=5, window_seconds=60, input_chars=12)
        assert exc.value.status == 429


def test_exact_money_requires_model_price_and_complete_integer_provider_usage(client, monkeypatch):
    user_id = learner(client)
    monkeypatch.setenv("AI_MAX_CALL_COST_MICROUSD", "100")
    monkeypatch.setenv("AI_PRICED_MODEL_ID", "priced-model")
    monkeypatch.setenv("AI_INPUT_MICROUSD_PER_MILLION_TOKENS", "1000000")
    monkeypatch.setenv("AI_OUTPUT_MICROUSD_PER_MILLION_TOKENS", "2000000")
    with session() as db:
        call = reserve(db, user_id)
        finish_ai_call(db, call, status="ready", usage={"prompt_tokens": 2, "completion_tokens": 3}, model_id="priced-model")
        db.commit()
        assert call.charged_micro_usd == 8
        assert call.cost_is_estimate is False
    with session() as db:
        call = reserve(db, user_id)
        finish_ai_call(db, call, status="ready", usage={"prompt_tokens": 2, "completion_tokens": True}, model_id="priced-model")
        db.commit()
        assert call.charged_micro_usd == 100
        assert call.cost_is_estimate is True
