"""Entitlements and a signed provider-neutral billing boundary.

No endpoint can grant itself a paid plan. Without explicitly configured service
adapters, checkout and incoming webhooks fail closed; no fake payments exist.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.account_services import aware, utcnow
from app.db.account_models import AccountSubscription, BillingEvent
from app.db.base import Base
from app.db.models import AIUsageLedger, User

PLANS = {"free": {"name": "Бесплатный", "ai_daily_calls": 20},
         "pro": {"name": "Pro", "ai_daily_calls": 100}}


def _https_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                    and not parsed.fragment and (parsed.port is None or 1 <= parsed.port <= 65535))
    except ValueError:
        return False


def checkout_config() -> tuple[str, str] | None:
    url, key = os.getenv("BILLING_CHECKOUT_URL", "").strip(), os.getenv("BILLING_API_KEY", "").strip()
    return (url, key) if _https_url(url) and key else None


def effective_subscription(db: Session, user_id: UUID) -> tuple[str, str, datetime | None]:
    row = db.get(AccountSubscription, user_id)
    if row is None:
        return "free", "active", None
    active = row.status == "active" and (row.period_end is None or aware(row.period_end) > utcnow())
    return (row.plan_id if active else "free", row.status if active or row.status != "active" else "expired", row.period_end)


def plan_entitlements(db: Session, user_id: UUID) -> dict[str, int]:
    plan_id, _, _ = effective_subscription(db, user_id)
    return {"ai_daily_calls": PLANS[plan_id]["ai_daily_calls"]}


def plans_response() -> dict:
    ready = checkout_config() is not None and len(os.getenv("BILLING_WEBHOOK_SECRET", "")) >= 32
    return {"plans": [{"id": plan_id, **definition, "checkout_available": ready and plan_id == "pro"}
                      for plan_id, definition in PLANS.items()]}


def billing_response(db: Session, user_id: UUID) -> dict:
    plan_id, status, period_end = effective_subscription(db, user_id)
    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = list(db.scalars(select(AIUsageLedger).where(AIUsageLedger.user_id == user_id, AIUsageLedger.created_at >= day_start)))
    calls = sum(not row.cache_hit for row in rows)
    cost, estimated = None, False
    reservations = Base.metadata.tables.get("ai_call_reservations")
    if reservations is not None and {"user_id", "created_at", "charged_micro_usd", "cost_is_estimate"} <= set(reservations.c.keys()):
        usage = db.execute(select(reservations.c.charged_micro_usd, reservations.c.cost_is_estimate)
                           .where(reservations.c.user_id == user_id, reservations.c.created_at >= day_start)).all()
        # Admission reservations are the quota source of truth, including
        # failures/restarts. Cache hits and rejected requests consume no slot.
        calls = len(usage)
        known = [row for row in usage if row.charged_micro_usd is not None]
        if known:
            cost = sum(row.charged_micro_usd for row in known)
            estimated = any(row.cost_is_estimate for row in known)
            if estimated and cost == 0:
                cost = None  # Missing prices do not mean the provider is free.
    return {"plan_id": plan_id, "status": status, "period_end": period_end,
            "entitlements": plan_entitlements(db, user_id),
            "usage": {"ai_calls_today": calls,
                      "input_tokens": sum(row.input_tokens for row in rows if row.input_tokens is not None),
                      "output_tokens": sum(row.output_tokens for row in rows if row.output_tokens is not None),
                      "estimated_cost_micro_usd": cost, "cost_is_estimate": estimated}}


class BillingWebhook(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    user_id: UUID
    plan_id: str = Field(pattern=r"^(free|pro)$")
    status: str = Field(pattern=r"^(active|cancelled|expired)$")
    occurred_at: datetime
    period_end: datetime | None = None


def apply_billing_event(db: Session, event: BillingWebhook, raw: bytes) -> dict:
    digest = hashlib.sha256(raw).hexdigest()
    user = db.scalar(select(User).where(User.id == event.user_id).with_for_update())
    if user is None:
        raise HTTPException(404, "Account not found")
    receipt = db.get(BillingEvent, event.event_id)
    if receipt is not None:
        if receipt.payload_digest != digest or receipt.user_id != user.id:
            raise HTTPException(409, "Billing event ID already used")
        return {"status": "duplicate"}
    now, event_time = utcnow(), aware(event.occurred_at)
    if event_time > now + timedelta(minutes=1) or event_time < now - timedelta(days=30):
        raise HTTPException(422, "Billing event time is invalid")
    if event.plan_id == "pro" and event.status == "active" and (
        event.period_end is None or not now < aware(event.period_end) <= now + timedelta(days=366)
    ):
        raise HTTPException(422, "A paid entitlement needs a valid expiry")
    row = db.get(AccountSubscription, user.id)
    stale = row is not None and aware(row.last_event_at) >= event_time
    if not stale:
        if row is None:
            row = AccountSubscription(user_id=user.id)
            db.add(row)
        row.plan_id, row.status, row.period_end, row.last_event_at = event.plan_id, event.status, event.period_end, event_time
    db.add(BillingEvent(event_id=event.event_id, user_id=user.id, payload_digest=digest))
    db.commit()
    return {"status": "ignored_stale" if stale else "applied"}


def create_checkout(user_id: UUID, plan_id: str) -> dict:
    config = checkout_config()
    if config is None or len(os.getenv("BILLING_WEBHOOK_SECRET", "")) < 32:
        raise HTTPException(503, "Billing checkout is not configured")
    url, key = config
    try:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            with client.stream("POST", url, headers={"Authorization": f"Bearer {key}",
                "Idempotency-Key": f"checkout-{user_id}-{plan_id}-{utcnow().strftime('%Y%m%d%H')}"},
                json={"user_id": str(user_id), "plan_id": plan_id}) as response:
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 32768:
                        raise ValueError("response too large")
                payload = json.loads(raw)
        checkout_url = payload.get("checkout_url") if isinstance(payload, dict) else None
        if not isinstance(checkout_url, str) or len(checkout_url) > 2048 or not _https_url(checkout_url):
            raise ValueError("invalid checkout")
        return {"checkout_url": checkout_url}
    except (httpx.HTTPError, ValueError, TypeError, UnicodeError):
        raise HTTPException(502, "Billing checkout is temporarily unavailable") from None
