"""End-to-end account mail over a real SMTP socket.

The suite runs a minimal SMTP server on loopback: the product opens a TCP
connection, speaks the protocol and hands over an RFC 5322 message, exactly as it
will against the operator's provider. Nothing inside the application is stubbed.
"""
import socketserver
import threading
from email import message_from_bytes, policy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import mailer
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.notifications import dispatch_outbox, email_available

PASSWORD = "Correct-Horse-Battery-9"


class SmtpSink:
    """Minimal SMTP server: accepts one message per connection and records it."""

    def __init__(self):
        self.messages: list[bytes] = []
        sink = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.wfile.write(b"220 sink ESMTP\r\n")
                data_mode, buffer = False, bytearray()
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    if data_mode:
                        if line in (b".\r\n", b".\n"):
                            sink.messages.append(bytes(buffer))
                            buffer.clear()
                            data_mode = False
                            self.wfile.write(b"250 queued\r\n")
                        else:
                            buffer.extend(line[1:] if line.startswith(b".") else line)
                        continue
                    verb = line.strip().split(b" ", 1)[0].upper()
                    if verb in (b"EHLO", b"HELO"):
                        self.wfile.write(b"250-sink\r\n250 SIZE 10485760\r\n")
                    elif verb in (b"MAIL", b"RCPT", b"RSET", b"NOOP"):
                        self.wfile.write(b"250 ok\r\n")
                    elif verb == b"DATA":
                        data_mode = True
                        self.wfile.write(b"354 end with .\r\n")
                    elif verb == b"QUIT":
                        self.wfile.write(b"221 bye\r\n")
                        return
                    else:
                        self.wfile.write(b"250 ok\r\n")

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def parsed(self):
        return [message_from_bytes(raw, policy=policy.default) for raw in self.messages]

    def bodies(self):
        return [part.get_content() for message in self.parsed() for part in message.walk()
                if part.get_content_type() == "text/plain"]

    def links(self):
        return [word.strip("<>()") for body in self.bodies() for word in body.split() if "token=" in word]


@pytest.fixture()
def mailbox(monkeypatch):
    sink = SmtpSink()
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", str(sink.port))
    monkeypatch.setenv("SMTP_FROM", "no-reply@localhost.test")
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    monkeypatch.setenv("SMTP_TLS", "none")
    monkeypatch.setenv("PUBLIC_WEB_URL", "http://127.0.0.1:3000")
    yield sink
    sink.close()


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(session_factory):
    from app.auth import _attempts

    _attempts.clear()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def drain(session_factory) -> dict:
    with session_factory() as db:
        return dispatch_outbox(db, limit=50)


def register(client, email: str) -> None:
    """Register and ask for the verification mail (that is when it is queued)."""
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("mentor_csrf") or ""
    queued = client.post("/auth/email-verification/request", headers={"X-CSRF-Token": csrf})
    assert queued.status_code == 200, queued.text


def verify(client, session_factory, mailbox) -> None:
    drain(session_factory)
    token = mailbox.links()[-1].split("token=", 1)[1]
    response = client.post("/auth/email-verification/confirm", json={"token": token})
    assert response.status_code == 200, response.text


def test_registration_mail_verifies_the_address(client, session_factory, mailbox):
    register(client, "verify-flow@example.com")
    result = drain(session_factory)
    assert result["delivered"] >= 1, result
    assert mailbox.messages, "письмо ушло через SMTP, а не в заглушку"
    message = mailbox.parsed()[0]
    assert message["From"] == "AI Python Mentor <no-reply@localhost.test>"
    assert "Подтвердите почту" in message["Subject"]

    token = mailbox.links()[-1].split("token=", 1)[1]
    confirmed = client.post("/auth/email-verification/confirm", json={"token": token})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "verified"

    again = client.post("/auth/email-verification/confirm", json={"token": token})
    assert again.status_code == 400, "ссылка одноразовая"


def test_password_reset_rotates_password_and_revokes_sessions(client, session_factory, mailbox):
    email = "reset-flow@example.com"
    register(client, email)
    verify(client, session_factory, mailbox)
    assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200

    requested = client.post("/auth/password-reset/request", json={"email": email})
    assert requested.status_code == 202, requested.text
    result = drain(session_factory)
    assert result["delivered"] >= 1, result
    reset_link = [link for link in mailbox.links() if "reset-password" in link][-1]
    reset = reset_link.split("token=", 1)[1]
    confirmed = client.post(
        "/auth/password-reset/confirm",
        json={"token": reset, "password": "Another-Correct-Horse-7"},
    )
    assert confirmed.status_code in (200, 204), confirmed.text
    assert client.get("/me").status_code == 401, "старая сессия отозвана"
    assert client.post("/auth/login", json={"email": email, "password": "Another-Correct-Horse-7"}).status_code == 200


def test_failed_login_notice_arrives_once_per_hour(client, session_factory, mailbox):
    email = "notice-flow@example.com"
    register(client, email)
    verify(client, session_factory, mailbox)
    before = len(mailbox.messages)
    for _ in range(3):
        assert client.post("/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
    drain(session_factory)
    assert len(mailbox.messages) == before + 1, "одно письмо на серию, а не три"
    assert any("Неудачные попытки" in message["Subject"] for message in mailbox.parsed())


def test_unknown_account_gets_no_mail_and_no_hint(client, session_factory, mailbox):
    before = len(mailbox.messages)
    response = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever-1234"})
    assert response.status_code == 401
    drain(session_factory)
    assert len(mailbox.messages) == before


def test_unconfigured_smtp_is_reported_as_unavailable(monkeypatch, client):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    assert email_available() is False
    response = client.post("/auth/password-reset/request", json={"email": "someone@example.com"})
    assert response.status_code == 202, "запрос сброса не раскрывает состояние канала"


def test_credentials_over_plaintext_are_refused(monkeypatch, mailbox):
    monkeypatch.setenv("SMTP_USER", "robot")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_TLS", "none")
    assert mailer.Settings.from_environment() is None


def test_template_rendering_and_unknown_template(mailbox):
    _subject, body = mailer.render("email_verify", {"token": "tok-123", "expires_at": "2026-11-11T20:00:00"})
    assert "tok-123" in body and "20:00" in body
    with pytest.raises(mailer.MailError):
        mailer.render("unknown_template", {})
