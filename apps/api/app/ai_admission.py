"""Database-backed, short-transaction admission before any external AI I/O."""
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_gateway import GatewayError
from app.db.domain_models import AICallReservation, AIRequestLease
from app.db.models import User

logger = logging.getLogger("ai.usage")


def _setting(name: str, default: int, *, maximum: int = 2_000_000_000) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        if not 0 <= value <= maximum:
            raise ValueError
        return value
    except ValueError:
        raise GatewayError(503, "AI admission settings are invalid") from None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


_spend_alerts: set[str] = set()


def _usd_limit_micro(name: str, default_usd: float) -> int:
    """Parse a USD limit into micro-USD; 0 disables the guard."""
    raw = os.getenv(name, "").strip()
    try:
        value = float(raw) if raw else float(default_usd)
    except ValueError:
        raise GatewayError(503, "AI spend limit is invalid") from None
    if not 0 <= value <= 100_000:
        raise GatewayError(503, "AI spend limit is invalid")
    return int(round(value * 1_000_000))


def _quota(reason: str) -> None:
    from app import metrics

    metrics.observe_quota(reason)


def _alert_daily_spend(day: str, spent: int, limit: int) -> None:
    """Emit one structured alert per UTC day when the soft threshold is crossed."""
    if day in _spend_alerts:
        return
    _spend_alerts.add(day)
    logger.info(json.dumps({"event": "ai_spend_alert", "day": day, "spent_micro_usd": spent,
                            "limit_micro_usd": limit, "ratio": round(spent / limit, 4)},
                           sort_keys=True))


def reserve_ai_call(
    db: Session, user_id, operation: str, request_key: str, *,
    limit: int, window_seconds: int, input_chars: int,
) -> AICallReservation:
    """Claim a fenced lease and reserve quota, committing before gateway I/O.

    PostgreSQL workers serialize only this bounded database transaction on the
    user row. Pending/failed calls consume quota too; restarting a worker does
    not reset a budget. An expired lease allows recovery but its old worker
    cannot publish a result after a new token has been issued.
    """
    now = datetime.now(timezone.utc)
    if not operation or len(operation) > 40 or not request_key or len(request_key) > 160 or input_chars < 0:
        raise ValueError("Invalid AI reservation")
    db.execute(select(User.id).where(User.id == user_id).with_for_update()).scalar_one()
    lease = db.get(AIRequestLease, (user_id, operation, request_key))
    if lease and lease.status == "processing" and _utc(lease.expires_at) > now:
        db.rollback()
        _quota("lease_busy")
        raise GatewayError(409, "AI request is already processing; retry later")
    count = db.scalar(select(func.count(AICallReservation.id)).where(
        AICallReservation.user_id == user_id,
        AICallReservation.operation == operation,
        AICallReservation.created_at >= now - timedelta(seconds=window_seconds),
    )) or 0
    if count >= limit:
        db.rollback()
        _quota("window_limit")
        raise GatewayError(429, "AI request limit exceeded; retry later")
    daily_limit = _setting("AI_DAILY_CALL_LIMIT", 100, maximum=100000)
    try:
        from app.billing import plan_entitlements
    except ImportError:
        plan_entitlements = None
    if plan_entitlements is not None:
        daily_limit = min(daily_limit, int(plan_entitlements(db, user_id).get("ai_daily_calls", daily_limit)))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_count, daily_cost = db.execute(select(
        func.count(AICallReservation.id),
        func.coalesce(func.sum(AICallReservation.charged_micro_usd), 0),
    ).where(AICallReservation.user_id == user_id, AICallReservation.created_at >= start)).one()
    budget = _setting("AI_DAILY_BUDGET_MICROUSD", 0)
    reservation_cost = _setting("AI_MAX_CALL_COST_MICROUSD", 0)
    if budget and not reservation_cost:
        db.rollback()
        raise GatewayError(503, "AI cost reservation must be configured when a budget is enabled")
    if daily_count >= daily_limit or budget and daily_cost + reservation_cost > budget:
        db.rollback()
        _quota("daily_budget")
        raise GatewayError(429, "Daily AI budget exceeded; retry tomorrow")
    # Installation-wide guard: every user shares one provider account, so a
    # single noisy tenant must not drain the day's budget.
    global_limit = _usd_limit_micro("AI_SPEND_DAILY_LIMIT_USD", 5.0)
    if global_limit:
        spent_today = db.scalar(select(
            func.coalesce(func.sum(AICallReservation.charged_micro_usd), 0),
        ).where(AICallReservation.created_at >= start)) or 0
        if spent_today + reservation_cost >= global_limit:
            db.rollback()
            _quota("global_budget")
            raise GatewayError(429, "Daily AI budget exhausted; retry tomorrow")
        if (spent_today + reservation_cost) * 10 >= global_limit * 8:
            _alert_daily_spend(start.date().isoformat(), int(spent_today + reservation_cost), global_limit)
    token = uuid4()
    if lease is None:
        lease = AIRequestLease(user_id=user_id, operation=operation, request_key=request_key)
        db.add(lease)
    lease.lease_token, lease.status = token, "processing"
    # Both embeddings and chat have a maximum configured timeout of 60s.
    lease.expires_at = now + timedelta(seconds=180)
    reservation = AICallReservation(
        user_id=user_id, operation=operation, request_key=request_key, lease_token=token,
        input_chars=input_chars, reserved_micro_usd=reservation_cost,
        charged_micro_usd=reservation_cost, cost_is_estimate=True, created_at=now,
    )
    db.add(reservation)
    db.commit()
    return reservation


def finish_ai_call(db: Session, reservation: AICallReservation, *, status: str, usage: dict | None = None, model_id: str | None = None) -> None:
    """Fence result publication. The caller atomically commits its result/ledger."""
    db.execute(select(User.id).where(User.id == reservation.user_id).with_for_update()).scalar_one()
    lease = db.get(AIRequestLease, (reservation.user_id, reservation.operation, reservation.request_key), populate_existing=True)
    if lease is None or lease.lease_token != reservation.lease_token or lease.status != "processing":
        raise GatewayError(409, "AI request lease expired; retry later")
    lease.status = "completed" if status in {"ready", "completed"} else "failed"
    reservation.status = status
    reservation.completed_at = datetime.now(timezone.utc)
    # Exact money amounts require deployment-owned prices and exact usage.
    # Missing provider telemetry stays explicitly estimated, including errors.
    input_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    output_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
    input_price = _setting("AI_INPUT_MICROUSD_PER_MILLION_TOKENS", 0)
    output_price = _setting("AI_OUTPUT_MICROUSD_PER_MILLION_TOKENS", 0)
    priced_model = os.getenv("AI_PRICED_MODEL_ID", "").strip()
    exact_usage = (type(input_tokens) is int and input_tokens >= 0
                   and type(output_tokens) is int and output_tokens >= 0)
    catalog_price = None
    if model_id and exact_usage:
        # Prices travel with the routing catalog, so a tier change cannot
        # silently keep charging the previous model's rate.
        try:
            from app.model_catalog import load as load_catalog

            catalog_price = load_catalog().price(model_id)
        except Exception:
            catalog_price = None
    if catalog_price is not None and exact_usage:
        reservation.charged_micro_usd = catalog_price.micro_usd(int(input_tokens or 0), int(output_tokens or 0))
        reservation.cost_is_estimate = False
    elif model_id and model_id == priced_model and exact_usage and input_price and output_price:
        reservation.charged_micro_usd = (int(input_tokens or 0) * input_price
                                       + int(output_tokens or 0) * output_price + 999999) // 1000000
        reservation.cost_is_estimate = False
