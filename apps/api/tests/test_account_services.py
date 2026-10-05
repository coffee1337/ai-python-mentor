import hashlib
import hmac
import json
import time
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, update

from app import notifications
from app.account_services import issue_token, owned_table_predicates, throttle, utcnow
from app.db.account_models import AccountToken, AdminAudit, AuthThrottle, NotificationOutbox, TelegramBinding
from app.db.models import AuthSession, MentorConversation, MentorMessage, User, UserSkill
from app.db.session import get_db
from app.main import app
from app.security import token_digest
from test_auth import client, csrf


def register(client, email="account@example.com"):
    response = client.post("/auth/register", json={"email": email, "password": "safe-password"})
    assert response.status_code == 201
    return UUID(response.json()["user"]["id"])


def session():
    return next(app.dependency_overrides[get_db]())


def post(client, path, data=None):
    return client.post(path, headers={"X-CSRF-Token": csrf(client)}, json=data)


def test_verification_is_single_use_and_never_stores_raw_token_in_token_table(client, monkeypatch):
    monkeypatch.setenv("DEV_ACCOUNT_TOKENS", "true")
    monkeypatch.setenv("APP_ENV", "development")
    user_id = register(client)
    assert client.post("/auth/email-verification/request").status_code == 403
    response = post(client, "/auth/email-verification/request")
    token = response.json()["development_token"]
    with session() as db:
        row = db.scalar(select(AccountToken).where(AccountToken.user_id == user_id))
        assert row.token_hash == token_digest(token)
        assert token not in row.token_hash
    assert client.post("/auth/email-verification/confirm", json={"token": token}).json() == {"status": "verified"}
    assert client.get("/me").json()["email_verified"] is True
    assert client.post("/auth/email-verification/confirm", json={"token": token}).status_code == 400
    with session() as db:
        assert db.scalar(select(NotificationOutbox).where(NotificationOutbox.user_id == user_id)).payload == {}


def test_expired_and_superseded_links_fail_and_production_dev_flag_is_ignored(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_ACCOUNT_TOKENS", "true")
    user_id = register(client)
    first = post(client, "/auth/email-verification/request").json()["development_token"]
    second = post(client, "/auth/email-verification/request").json()["development_token"]
    assert client.post("/auth/email-verification/confirm", json={"token": first}).status_code == 400
    with session() as db:
        db.execute(update(AccountToken).where(AccountToken.token_hash == token_digest(second)).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()
    assert client.post("/auth/email-verification/confirm", json={"token": second}).status_code == 400
    monkeypatch.setenv("APP_ENV", "production")
    assert post(client, "/auth/email-verification/request").status_code == 503
    assert notifications.development_mail_enabled() is False


def test_reset_changes_password_revokes_every_session_and_rejects_replay(client, monkeypatch):
    monkeypatch.setenv("DEV_ACCOUNT_TOKENS", "true")
    monkeypatch.setenv("APP_ENV", "development")
    user_id = register(client)
    with session() as db:
        from app.auth import _create_session
        _create_session(db, db.get(User, user_id))
        db.commit()
    response = client.post("/auth/password-reset/request", json={"email": "account@example.com"})
    assert response.status_code == 202
    token = response.json()["development_token"]
    result = client.post("/auth/password-reset/confirm", json={"token": token, "password": "new-password"})
    assert result.json() == {"status": "reset"}
    assert client.get("/me").status_code == 401
    with session() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))) == 0
    assert client.post("/auth/password-reset/confirm", json={"token": token, "password": "other-password"}).status_code == 400
    assert client.post("/auth/login", json={"email": "account@example.com", "password": "safe-password"}).status_code == 401
    assert client.post("/auth/login", json={"email": "account@example.com", "password": "new-password"}).status_code == 200


def test_password_change_requires_csrf_and_current_password_and_revokes_sessions(client):
    user_id = register(client)
    with session() as db:
        reset_token, _ = issue_token(db, user_id, "password_reset", 30)
        db.commit()
    data = {"current_password": "safe-password", "password": "changed-password"}
    assert client.post("/me/password", json=data).status_code == 403
    assert post(client, "/me/password", {**data, "current_password": "wrong-password"}).status_code == 403
    assert post(client, "/me/password", data).json()["reauthentication_required"] is True
    assert client.get("/me").status_code == 401
    assert client.post("/auth/password-reset/confirm", json={"token": reset_token, "password": "other-password"}).status_code == 400
    assert client.post("/auth/login", json={"email": "account@example.com", "password": "safe-password"}).status_code == 401
    assert client.post("/auth/login", json={"email": "account@example.com", "password": "changed-password"}).status_code == 200


def test_reset_response_does_not_enumerate_accounts_or_invent_delivery(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEV_ACCOUNT_TOKENS", "true")
    register(client)
    known = client.post("/auth/password-reset/request", json={"email": "account@example.com"})
    unknown = client.post("/auth/password-reset/request", json={"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"status": "accepted"}
    with session() as db:
        assert db.scalar(select(func.count()).select_from(AccountToken)) == 0


def test_auth_admission_is_durable_across_sessions_and_process_counter_clear(client):
    register(client)
    with session() as db:
        throttle(db, scope="test", subject="same-account", limit=2)
    from app.auth import _attempts
    _attempts.clear()
    with session() as db:
        throttle(db, scope="test", subject="same-account", limit=2)
    with session() as db:
        with pytest.raises(HTTPException) as error:
            throttle(db, scope="test", subject="same-account", limit=2)
        assert error.value.status_code == 429
        rows = list(db.scalars(select(AuthThrottle)))
        assert all("@" not in row.key and "same-account" not in row.key for row in rows)


def test_sessions_are_owned_and_current_revocation_clears_cookies(client):
    register(client)
    listing = client.get("/me/sessions").json()["sessions"]
    assert len(listing) == 1 and listing[0]["is_current"] is True
    own = listing[0]["id"]
    assert "token_hash" not in json.dumps(listing)
    assert client.post(f"/me/sessions/{own}/revoke").status_code == 403
    post(client, "/auth/logout")
    register(client, "other@example.com")
    assert post(client, f"/me/sessions/{own}/revoke").status_code == 404
    current = client.get("/me/sessions").json()["sessions"][0]["id"]
    assert post(client, f"/me/sessions/{current}/revoke").status_code == 204
    assert client.get("/me").status_code == 401


def test_export_and_transactional_delete_include_derived_rows_and_preserve_other_user(client):
    first = register(client)
    post(client, "/auth/logout")
    second = register(client, "other@example.com")
    post(client, "/auth/logout")
    client.post("/auth/login", json={"email": "account@example.com", "password": "safe-password"})
    with session() as db:
        conversation = MentorConversation(user_id=first, lesson_id="variables-v1")
        db.add(conversation); db.flush()
        db.add(MentorMessage(conversation_id=conversation.id, role="user", content="private learner text"))
        db.add(TelegramBinding(user_id=first, chat_id="12345"))
        raw, expiry = issue_token(db, first, "email_verify", 15)
        notifications.enqueue(db, user_id=first, channel="email", template="email_verify",
                              payload={"token": raw}, idempotency_key="private-token")
        db.commit()
    response = client.get("/me/export")
    assert response.status_code == 200
    text = response.text
    assert "private learner text" in text and "12345" in text
    assert raw not in text and "password_hash" not in text and "csrf_token_hash" not in text
    assert "other@example.com" not in text
    assert post(client, "/me/delete", {"password": "wrong-password", "confirmation": "DELETE"}).status_code == 403
    assert post(client, "/me/delete", {"password": "safe-password", "confirmation": "DELETE"}).status_code == 204
    with session() as db:
        assert db.get(User, first) is None and db.get(User, second) is not None
        for table, predicate in owned_table_predicates(first).items():
            assert db.scalar(select(func.count()).select_from(table).where(predicate)) == 0
        assert db.scalar(select(func.count()).select_from(MentorMessage)) == 0
    assert client.get("/me").status_code == 401


def test_preferences_and_telegram_binding_require_csrf_secret_ownership_and_one_use(client, monkeypatch):
    user_id = register(client)
    assert client.patch("/me/notifications", json={"telegram_enabled": True}).status_code == 403
    assert client.patch("/me/notifications", headers={"X-CSRF-Token": csrf(client)}, json={"telegram_enabled": "yes"}).status_code == 422
    assert post(client, "/me/telegram/bind-token").status_code == 503
    secret = "t" * 40
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", secret)
    raw = post(client, "/me/telegram/bind-token").json()["token"]
    data = {"message": {"chat": {"id": 123, "type": "private"}, "from": {"id": 123}, "text": "/start " + raw}}
    assert client.post("/webhooks/telegram", json=data).status_code == 403
    assert client.post("/webhooks/telegram", headers={"X-Telegram-Bot-Api-Secret-Token": secret}, json=data).json() == {"status": "bound"}
    assert client.get("/me/notifications").json()["telegram_bound"] is True
    assert client.post("/webhooks/telegram", headers={"X-Telegram-Bot-Api-Secret-Token": secret}, json=data).status_code == 400
    assert post(client, "/me/telegram/unbind").status_code == 204
    assert client.get("/me/notifications").json()["telegram_bound"] is False


def signed_event(client, secret, event, *, timestamp=None):
    raw = json.dumps(event, separators=(",", ":")).encode()
    stamp = str(timestamp if timestamp is not None else int(time.time()))
    signature = hmac.new(secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return client.post("/webhooks/billing", content=raw, headers={"Content-Type": "application/json",
        "X-Webhook-Timestamp": stamp, "X-Webhook-Signature": signature})


def test_billing_is_fail_closed_signed_idempotent_and_expiring(client, monkeypatch):
    user_id = register(client)
    assert client.get("/me/billing").json()["plan_id"] == "free"
    assert post(client, "/billing/checkout", {"plan_id": "pro"}).status_code == 503
    assert client.post("/webhooks/billing", json={}).status_code == 503
    secret = "b" * 40
    monkeypatch.setenv("BILLING_WEBHOOK_SECRET", secret)
    now = utcnow()
    event = {"event_id": "event-one", "user_id": str(user_id), "plan_id": "pro", "status": "active",
             "occurred_at": now.isoformat(), "period_end": (now + timedelta(days=30)).isoformat()}
    assert client.post("/webhooks/billing", json=event).status_code == 403
    assert signed_event(client, secret, event, timestamp=int(time.time()) - 600).status_code == 403
    assert signed_event(client, secret, event).json() == {"status": "applied"}
    assert signed_event(client, secret, event).json() == {"status": "duplicate"}
    assert client.get("/me/billing").json()["entitlements"]["ai_daily_calls"] == 100
    event["plan_id"] = "free"
    assert signed_event(client, secret, event).status_code == 409
    from app.db.account_models import AccountSubscription
    with session() as db:
        db.get(AccountSubscription, user_id).period_end = now - timedelta(seconds=1)
        db.commit()
    assert client.get("/me/billing").json()["plan_id"] == "free"


def test_outbox_preferences_and_idempotency_prevent_unwanted_delivery(client, monkeypatch):
    user_id = register(client)
    with session() as db:
        db.get(User, user_id).email_verified = True
        db.add(UserSkill(user_id=user_id, skill_id="python.variables", next_review_at=utcnow() - timedelta(minutes=1)))
        db.commit()
        assert notifications.enqueue_due_reviews(db) == 1
        assert notifications.enqueue_due_reviews(db) == 0
        assert notifications.dispatch_outbox(db)["blocked"] == 1
    response = client.patch("/me/notifications", headers={"X-CSRF-Token": csrf(client)}, json={"review_reminders": False})
    assert response.status_code == 200
    called = []
    monkeypatch.setattr(notifications, "_deliver", lambda *args: called.append(True))
    with session() as db:
        assert notifications.dispatch_outbox(db)["cancelled"] == 1
    assert not called


def test_admin_role_is_server_allowlisted_and_actions_are_audited(client, monkeypatch):
    user_id = register(client)
    assert client.get("/admin/metrics").status_code == 403
    monkeypatch.setenv("ADMIN_USER_IDS", str(user_id))
    assert client.get("/admin/metrics").status_code == 200
    assert client.post(f"/admin/users/{user_id}/revoke-sessions").status_code == 403
    response = post(client, f"/admin/users/{user_id}/revoke-sessions")
    assert response.json()["revoked"] == 1
    with session() as db:
        assert db.scalar(select(AdminAudit)).action == "revoke_sessions"


def test_tutor_transport_retry_keeps_committed_reply(client, monkeypatch):
    user_id = register(client)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:" + "a" * 24)
    calls = []
    def delivery(db, row):
        current = db.get(NotificationOutbox, row.id)
        calls.append(current.payload.copy())
        if "reply" not in current.payload:
            current.payload = {"chat_id": "123", "reply": "Saved answer"}
            db.commit()
            raise HTTPException(502, "Transport unavailable")
    monkeypatch.setattr(notifications, "_deliver", delivery)
    with session() as db:
        db.add(TelegramBinding(user_id=user_id, chat_id="123"))
        notifications.enqueue(db, user_id=user_id, channel="telegram", template="telegram_tutor",
                              payload={"chat_id": "123", "question": "Question"}, idempotency_key="retry-tutor")
        db.commit()
        assert notifications.dispatch_outbox(db)["failed"] == 1
        row = db.scalar(select(NotificationOutbox).where(NotificationOutbox.user_id == user_id))
        assert row.payload == {"chat_id": "123", "reply": "Saved answer"}
        row.available_at = utcnow() - timedelta(seconds=1)
        db.commit()
        assert notifications.dispatch_outbox(db)["delivered"] == 1
    assert calls == [{"chat_id": "123", "question": "Question"}, {"chat_id": "123", "reply": "Saved answer"}]
