"""Owned account APIs and separately authenticated integration webhooks."""
from __future__ import annotations

import hmac
import json
import os
import time
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app import billing, notifications
from app.account_services import consume_token, delete_account, export_account, issue_token, revoke_sessions, throttle, utcnow
from app.auth import _clear_auth_cookies, csrf_protected, current_auth
from app.db.account_models import AccountToken, AdminAudit, NotificationOutbox, NotificationPreference, TelegramBinding
from app.db.models import AIUsageLedger, AuthSession, CodingAttempt, User
from app.db.session import get_db
from app.security import hash_password, normalize_email, signed_payload_valid, verify_password

router = APIRouter(tags=["accounts"])


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TokenRequest(StrictRequest):
    token: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class PasswordResetRequest(StrictRequest):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value: str) -> str:
        value = normalize_email(value)
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Enter a valid email address")
        return value


class PasswordResetConfirm(TokenRequest):
    password: str = Field(min_length=8, max_length=256)


class PasswordChangeRequest(StrictRequest):
    current_password: str = Field(min_length=8, max_length=256)
    password: str = Field(min_length=8, max_length=256)


class DeleteAccountRequest(StrictRequest):
    password: str = Field(min_length=8, max_length=256)
    confirmation: str = Field(pattern=r"^DELETE$")


class NotificationPatch(StrictRequest):
    email_enabled: StrictBool | None = None
    telegram_enabled: StrictBool | None = None
    review_reminders: StrictBool | None = None


class CheckoutRequest(StrictRequest):
    plan_id: str = Field(pattern=r"^pro$")


class BoundedAction(StrictRequest):
    limit: int = Field(default=25, ge=1, le=100)


def _development_token(raw: str | None) -> dict:
    return {"development_token": raw} if notifications.development_mail_enabled() else {}


@router.post("/auth/email-verification/request")
def request_verification(auth=Depends(csrf_protected), db: Session = Depends(get_db)):
    user, _ = auth
    throttle(db, scope="verify_user", subject=str(user.id), limit=5, window_seconds=3600)
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    if user.email_verified:
        return {"status": "verified"}
    raw, expiry = issue_token(db, user.id, "email_verify", 60)
    notifications.enqueue_account_mail(db, user.id, "email_verify", raw, expiry)
    db.commit()
    return {"status": "queued", **_development_token(raw)}


@router.post("/auth/email-verification/confirm")
def confirm_verification(payload: TokenRequest, request: Request, db: Session = Depends(get_db)):
    throttle(db, scope="token_confirm_ip", subject=request.client.host if request.client else "unknown", limit=20)
    user = consume_token(db, payload.token, "email_verify")
    user.email_verified = True
    db.execute(update(NotificationOutbox).where(NotificationOutbox.user_id == user.id,
        NotificationOutbox.template == "email_verify", NotificationOutbox.status != "delivered")
        .values(status="cancelled", payload={}))
    db.commit()
    return {"status": "verified"}


@router.post("/auth/password-reset/request", status_code=202)
def request_password_reset(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    throttle(db, scope="reset_ip", subject=request.client.host if request.client else "unknown", limit=20)
    throttle(db, scope="reset_account", subject=payload.email, limit=5, window_seconds=3600)
    user = db.scalar(select(User).where(User.email == payload.email, User.is_active.is_(True)).with_for_update())
    raw = None
    if user is not None and (notifications.email_configuration() is not None or notifications.development_mail_enabled()):
        raw, expiry = issue_token(db, user.id, "password_reset", 30)
        notifications.enqueue_account_mail(db, user.id, "password_reset", raw, expiry)
        db.commit()
    # Same production response for unknown accounts and unavailable delivery.
    return {"status": "accepted", **_development_token(raw)}


@router.post("/auth/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirm, request: Request, response: Response,
                           db: Session = Depends(get_db)):
    throttle(db, scope="token_confirm_ip", subject=request.client.host if request.client else "unknown", limit=20)
    user = consume_token(db, payload.token, "password_reset")
    user.password_hash = hash_password(payload.password)
    user.email_verified = True  # Possession of the delivered mailbox link proves ownership.
    revoke_sessions(db, user.id)
    db.execute(update(AccountToken).where(AccountToken.user_id == user.id, AccountToken.purpose == "password_reset",
        AccountToken.used_at.is_(None)).values(used_at=utcnow()))
    db.execute(update(NotificationOutbox).where(NotificationOutbox.user_id == user.id,
        NotificationOutbox.template == "password_reset", NotificationOutbox.status != "delivered")
        .values(status="cancelled", payload={}))
    db.commit()
    _clear_auth_cookies(response)
    return {"status": "reset"}


@router.get("/me/sessions")
def sessions(auth=Depends(current_auth), db: Session = Depends(get_db)):
    user, current = auth
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)
                      .order_by(AuthSession.created_at.desc()).limit(100))
    return {"sessions": [{"id": row.id, "created_at": row.created_at, "last_seen_at": row.last_seen_at,
        "expires_at": row.expires_at, "revoked_at": row.revoked_at, "is_current": row.id == current.id} for row in rows]}


@router.post("/me/password")
def change_password(payload: PasswordChangeRequest, response: Response,
                    auth=Depends(csrf_protected), db: Session = Depends(get_db)):
    user, _ = auth
    throttle(db, scope="password_user", subject=str(user.id), limit=5)
    user = db.scalar(select(User).where(User.id == user.id).with_for_update(), execution_options={"populate_existing": True})
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(403, "Current password is incorrect")
    user.password_hash = hash_password(payload.password)
    revoke_sessions(db, user.id)
    db.execute(update(AccountToken).where(AccountToken.user_id == user.id,
        AccountToken.purpose == "password_reset", AccountToken.used_at.is_(None)).values(used_at=utcnow()))
    db.execute(update(NotificationOutbox).where(NotificationOutbox.user_id == user.id,
        NotificationOutbox.template == "password_reset", NotificationOutbox.status != "delivered")
        .values(status="cancelled", payload={}))
    db.commit()
    _clear_auth_cookies(response)
    return {"status": "changed", "reauthentication_required": True}


@router.post("/me/sessions/{session_id}/revoke", status_code=204)
def revoke_session(session_id: UUID, response: Response, auth=Depends(csrf_protected), db: Session = Depends(get_db)):
    user, current = auth
    row = db.scalar(select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == user.id).with_for_update())
    if row is None:
        raise HTTPException(404, "Session not found")
    row.revoked_at = utcnow()
    db.commit()
    if row.id == current.id:
        _clear_auth_cookies(response)


@router.get("/me/export")
def export(auth=Depends(current_auth), db: Session = Depends(get_db)):
    return export_account(db, auth[0].id)


@router.post("/me/delete", status_code=204)
def remove_account(payload: DeleteAccountRequest, response: Response, auth=Depends(csrf_protected), db: Session = Depends(get_db)):
    user, _ = auth
    throttle(db, scope="delete_user", subject=str(user.id), limit=5)
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(403, "Password confirmation failed")
    user_id, email = user.id, user.email
    delete_account(db, user_id, email=email)
    _clear_auth_cookies(response)


@router.get("/me/notifications")
def preferences(auth=Depends(current_auth), db: Session = Depends(get_db)):
    return notifications.preferences_response(db, auth[0].id)


@router.patch("/me/notifications")
def update_preferences(payload: NotificationPatch, auth=Depends(csrf_protected), db: Session = Depends(get_db)):
    user, _ = auth
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    row = db.get(NotificationPreference, user.id)
    if row is None:
        row = NotificationPreference(user_id=user.id)
        db.add(row)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    db.commit()
    return notifications.preferences_response(db, user.id)


@router.post("/me/telegram/bind-token")
def telegram_token(auth=Depends(csrf_protected), db: Session = Depends(get_db)):
    user, _ = auth
    if len(os.getenv("TELEGRAM_WEBHOOK_SECRET", "")) < 32:
        raise HTTPException(503, "Telegram binding is not configured")
    throttle(db, scope="telegram_bind_user", subject=str(user.id), limit=5, window_seconds=3600)
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    raw, expiry = issue_token(db, user.id, "telegram_bind", 15)
    db.commit()
    username = os.getenv("TELEGRAM_BOT_USERNAME", "").strip()
    return {"token": raw, "expires_at": expiry, "bot_username": username or None}


@router.post("/me/telegram/unbind", status_code=204)
def unbind_telegram(auth=Depends(csrf_protected), db: Session = Depends(get_db)):
    user, _ = auth
    db.execute(delete(TelegramBinding).where(TelegramBinding.user_id == user.id))
    db.execute(update(AccountToken).where(AccountToken.user_id == user.id, AccountToken.purpose == "telegram_bind")
               .values(used_at=utcnow()))
    db.execute(update(NotificationOutbox).where(NotificationOutbox.user_id == user.id, NotificationOutbox.channel == "telegram",
        NotificationOutbox.status != "delivered").values(status="cancelled", payload={}))
    db.commit()


async def _bounded_body(request: Request) -> bytes:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(413, "Webhook body exceeds the limit")
    return bytes(raw)


@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request, db: Session = Depends(get_db),
                           secret_header: str | None = Header(None, alias="X-Telegram-Bot-Api-Secret-Token")):
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "Telegram webhook is not configured")
    if secret_header is None or not hmac.compare_digest(secret_header, secret):
        raise HTTPException(403, "Webhook authentication failed")
    raw = await _bounded_body(request)
    try:
        update_payload = json.loads(raw)
        message = update_payload.get("message", {})
        chat, sender = message.get("chat", {}), message.get("from", {})
        text, chat_id, sender_id = message.get("text", ""), chat.get("id"), sender.get("id")
        if chat.get("type") != "private" or type(chat_id) is not int or type(sender_id) is not int or chat_id != sender_id:
            return {"status": "ignored"}
        if not isinstance(text, str) or not text.strip():
            return {"status": "ignored"}
        if not text.startswith("/start "):
            update_id = update_payload.get("update_id")
            if type(update_id) is not int or update_id < 0 or len(text) > 4000:
                raise ValueError()
            return notifications.enqueue_telegram_question(db, str(chat_id), update_id, text.strip())
        if len(text) > 140:
            raise ValueError()
        payload = TokenRequest(token=text[7:].strip())
    except (ValueError, TypeError, AttributeError, ValidationError):
        raise HTTPException(422, "Invalid Telegram update") from None
    notifications.bind_telegram(db, payload.token, str(chat_id))
    return {"status": "bound"}


@router.get("/billing/plans")
def plans():
    return billing.plans_response()


@router.get("/me/billing")
def account_billing(auth=Depends(current_auth), db: Session = Depends(get_db)):
    return billing.billing_response(db, auth[0].id)


@router.post("/billing/checkout")
def checkout(payload: CheckoutRequest, auth=Depends(csrf_protected), db: Session = Depends(get_db)):
    throttle(db, scope="checkout_user", subject=str(auth[0].id), limit=5)
    return billing.create_checkout(auth[0].id, payload.plan_id)


@router.post("/webhooks/billing")
async def billing_webhook(request: Request, db: Session = Depends(get_db),
                          timestamp: str | None = Header(None, alias="X-Webhook-Timestamp"),
                          signature: str | None = Header(None, alias="X-Webhook-Signature")):
    secret = os.getenv("BILLING_WEBHOOK_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "Billing webhook is not configured")
    raw = await _bounded_body(request)
    if not signed_payload_valid(raw, timestamp or "", signature or "", secret, now=int(time.time())):
        raise HTTPException(403, "Webhook authentication failed")
    try:
        event = billing.BillingWebhook.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Invalid billing event") from None
    return billing.apply_billing_event(db, event, raw)


def admin_auth(auth=Depends(current_auth)):
    configured = {value.strip() for value in os.getenv("ADMIN_USER_IDS", "").split(",") if value.strip()}
    if str(auth[0].id) not in configured:
        raise HTTPException(403, "Administrator access required")
    return auth


def admin_csrf(auth=Depends(csrf_protected)):
    return admin_auth(auth)


@router.get("/admin/metrics")
def metrics(auth=Depends(admin_auth), db: Session = Depends(get_db)):
    now = utcnow()
    return {"users": db.scalar(select(func.count()).select_from(User)),
            "active_sessions": db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)),
            "notification_statuses": dict(db.execute(select(NotificationOutbox.status, func.count()).group_by(NotificationOutbox.status)).all()),
            "runner_statuses": dict(db.execute(select(CodingAttempt.status, func.count()).group_by(CodingAttempt.status)).all()),
            "ai_statuses": dict(db.execute(select(AIUsageLedger.status, func.count()).where(AIUsageLedger.created_at >= now - timedelta(days=1)).group_by(AIUsageLedger.status)).all())}


@router.get("/admin/usage")
def usage(auth=Depends(admin_auth), db: Session = Depends(get_db)):
    rows = db.execute(select(AIUsageLedger.operation, func.count(), func.sum(AIUsageLedger.input_tokens), func.sum(AIUsageLedger.output_tokens))
        .where(AIUsageLedger.created_at >= utcnow() - timedelta(days=1)).group_by(AIUsageLedger.operation)).all()
    return {"window_hours": 24, "operations": [{"operation": row[0], "requests": row[1], "input_tokens": row[2], "output_tokens": row[3]} for row in rows]}


@router.post("/admin/users/{user_id}/revoke-sessions")
def admin_revoke(user_id: UUID, auth=Depends(admin_csrf), db: Session = Depends(get_db)):
    if db.get(User, user_id) is None:
        raise HTTPException(404, "Account not found")
    count = revoke_sessions(db, user_id)
    db.add(AdminAudit(actor_id=auth[0].id, target_id=user_id, action="revoke_sessions", result_count=count))
    db.commit()
    return {"revoked": count}


@router.post("/admin/notifications/enqueue-reviews")
def enqueue_reviews(payload: BoundedAction, auth=Depends(admin_csrf), db: Session = Depends(get_db)):
    count = notifications.enqueue_due_reviews(db, limit=payload.limit)
    db.add(AdminAudit(actor_id=auth[0].id, action="enqueue_reviews", result_count=count))
    db.commit()
    return {"queued": count}


@router.post("/admin/notifications/dispatch")
def dispatch(payload: BoundedAction, auth=Depends(admin_csrf), db: Session = Depends(get_db)):
    result = notifications.dispatch_outbox(db, limit=payload.limit)
    db.add(AdminAudit(actor_id=auth[0].id, action="dispatch_notifications", result_count=sum(result.values())))
    db.commit()
    return result
