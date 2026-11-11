"""ASVS controls: breached passwords and absolute session lifetime."""
import hashlib
from datetime import UTC, datetime, timedelta

import httpx
from test_auth import client, csrf

from app import passwords
from app.db.models import AuthSession
from app.db.session import get_db
from app.main import app


def test_breach_check_reads_the_suffix_from_the_range_response(monkeypatch):
    secret = "Correct-Horse-Battery-2026"
    digest = hashlib.sha1(secret.encode()).hexdigest().upper()
    body = f"0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n{digest[5:]}:42"
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    assert passwords.breach_count(secret, transport=transport) == 42
    assert passwords.breach_count("another-password-entirely", transport=transport) == 0


def test_breach_check_failure_is_soft(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("offline", request=request)

    transport = httpx.MockTransport(boom)
    assert passwords.breach_count("whatever-password", transport=transport) is None


def test_registration_rejects_a_breached_password(client, monkeypatch):
    monkeypatch.setattr(passwords, "is_breached", lambda password, **kwargs: password == "Breached-Password-2026")
    rejected = client.post("/auth/register", json={
        "email": "breached@example.invalid", "password": "Breached-Password-2026"})
    assert rejected.status_code == 400
    accepted = client.post("/auth/register", json={
        "email": "not-breached@example.invalid", "password": "Fresh-Password-2026"})
    assert accepted.status_code == 201


def test_session_older_than_the_absolute_window_is_rejected(client):
    register = client.post("/auth/register", json={
        "email": "absolute@example.invalid", "password": "Absolute-Password-2026"})
    assert register.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        session = db.query(AuthSession).filter(AuthSession.revoked_at.is_(None)).one()
        session.created_at = datetime.now(UTC) - timedelta(days=31)
        session.expires_at = datetime.now(UTC) + timedelta(days=30)
        db.commit()
    assert client.get("/me").status_code == 401
