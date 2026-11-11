"""Telegram channel end to end against a local Bot API mock.

Nothing here talks to telegram.org: the product code builds real HTTP requests,
signs them with the configured token and parses real responses, while the mock
server records what the bot tried to send. The binding, the commands and the quiz
answer all run through the webhook exactly as they will in production.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.account_models import NotificationOutbox, TelegramBinding, TelegramUpdate
from app.db.base import Base
from app.db.models import SkillEvidence
from app.db.session import get_db
from app.main import app

PASSWORD = "Correct-Horse-Battery-9"
SECRET = "webhook-secret-0123456789abcdefghijklmnop"
TOKEN = "123456789:local-test-token-value"


class TelegramMock:
    def __init__(self):
        self.calls: list[dict] = []
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                mock.calls.append({"method": self.path.rsplit("/", 1)[-1], "body": body})
                payload = json.dumps({"ok": True, "result": {"message_id": len(mock.calls)}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def texts(self):
        return [call["body"].get("text", "") for call in self.calls if call["method"] == "sendMessage"]

    def last(self) -> dict:
        return self.calls[-1]["body"] if self.calls else {}


@pytest.fixture()
def telegram(monkeypatch):
    mock = TelegramMock()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "nastavn1kAI_bot")
    monkeypatch.setenv("TELEGRAM_API_BASE", mock.base)
    yield mock
    mock.close()


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


def register(client, email="bot-flow@example.com"):
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    onboarding = client.post("/onboarding", json={"experience_level": "beginner",
                                                  "target_role": "Python backend", "weekly_minutes": 180},
                             headers={"X-CSRF-Token": client.cookies.get("mentor_csrf") or ""})
    assert onboarding.status_code in (200, 201), onboarding.text
    return email


def bind_code(client) -> str:
    response = client.post("/me/telegram/bind-token",
                           headers={"X-CSRF-Token": client.cookies.get("mentor_csrf") or ""})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def update(message: dict, update_id: int) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": 777, "type": "private"}, "from": {"username": "learner"}, **message}}


def deliver(client, payload: dict, *, header=SECRET, secret=SECRET):
    return client.post(f"/telegram/webhook/{secret}", json=payload,
                       headers={"X-Telegram-Bot-Api-Secret-Token": header})


def test_status_reports_the_channel_as_configured(client, telegram):
    status = client.get("/telegram/status")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["bot_username"] == "nastavn1kAI_bot"


def test_binding_then_today_progress_and_quiz(client, session_factory, telegram):
    register(client)
    code = bind_code(client)

    bound = deliver(client, update({"text": f"/start {code}"}, 1001))
    assert bound.status_code == 200, bound.text
    assert "привязан" in telegram.texts()[-1].lower()
    with session_factory() as db:
        binding = db.get(TelegramBinding, *db.scalars(select(TelegramBinding.user_id)).all()[:1])
        assert binding is not None and binding.revoked_at is None

    assert deliver(client, update({"text": "/today"}, 1002)).status_code == 200
    assert "Сегодня" in telegram.texts()[-1]

    assert deliver(client, update({"text": "/progress"}, 1003)).status_code == 200
    assert "Пройдено уроков" in telegram.texts()[-1]

    assert deliver(client, update({"text": "/quiz"}, 1004)).status_code == 200
    keyboard = telegram.last().get("reply_markup", {}).get("inline_keyboard", [])
    assert keyboard, "quiz offers inline answers"
    data = keyboard[0][0]["callback_data"]
    lesson_id, question_id, index = data.split(":", 3)[1:]

    callback = {"update_id": 1005, "callback_query": {"id": "cb-1", "data": data,
                "message": {"message_id": 42, "chat": {"id": 777}}}}
    assert deliver(client, callback).status_code == 200
    with session_factory() as db:
        evidence = db.scalars(select(SkillEvidence).where(SkillEvidence.source_type == "knowledge_check_attempt")).all()
        assert evidence, "ответ из Telegram записан в прогресс"
        assert any((row.evidence_metadata or {}).get("channel") == "telegram" for row in evidence)
    assert any("Записано" in str(call["body"].get("text", "")) for call in telegram.calls)

    assert deliver(client, update({"text": "/help"}, 1006)).status_code == 200
    assert "/quiz" in telegram.texts()[-1]
    assert lesson_id and question_id is not None and index.isdigit()


def test_unlink_revokes_binding_and_stops_delivery(client, session_factory, telegram):
    register(client)
    code = bind_code(client)
    deliver(client, update({"text": f"/link {code}"}, 2001))
    assert deliver(client, update({"text": "/unlink"}, 2002)).status_code == 200
    assert "отвязан" in telegram.texts()[-1].lower()
    with session_factory() as db:
        binding = db.scalars(select(TelegramBinding)).first()
        assert binding.revoked_at is not None, "история сохранена"
        assert binding.chat_id.startswith("revoked-"), "chat id освобождён"
        queued = db.scalars(select(NotificationOutbox).where(
            NotificationOutbox.channel == "telegram", NotificationOutbox.status != "delivered")).all()
        assert all(row.status == "cancelled" for row in queued)

    before = len(telegram.texts())
    deliver(client, update({"text": "/today"}, 2003))
    assert len(telegram.texts()) == before + 1
    assert "не привязан" in telegram.texts()[-1]


def test_repeated_update_id_is_applied_once(client, session_factory, telegram):
    register(client)
    code = bind_code(client)
    payload = update({"text": f"/link {code}"}, 3001)
    assert deliver(client, payload).status_code == 200
    sent = len(telegram.texts())
    again = deliver(client, payload)
    assert again.status_code == 200 and again.json().get("duplicate") is True
    assert len(telegram.texts()) == sent
    with session_factory() as db:
        assert len(db.scalars(select(TelegramUpdate)).all()) == 1


def test_webhook_rejects_bad_secret_header_and_unknown_updates(client, telegram):
    assert deliver(client, update({"text": "/help"}, 4001), header="nope").status_code == 403
    assert deliver(client, update({"text": "/help"}, 4002), secret="x" * 32).status_code == 404
    unsupported = {"update_id": 4003, "edited_message": {"chat": {"id": 777}, "text": "x"}}
    assert deliver(client, unsupported).status_code == 400
    assert deliver(client, {"no_update_id": True}).status_code == 400


def test_channel_is_unavailable_without_configuration(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert client.get("/telegram/status").json()["configured"] is False
    response = deliver(client, update({"text": "/help"}, 5001))
    assert response.status_code == 503


def test_binding_code_is_single_use(client, telegram):
    register(client)
    code = bind_code(client)
    assert "привязан" in _bind(client, telegram, code, 6001)
    second = _bind(client, telegram, code, 6002, chat=888)
    assert "недействителен" in second.lower()


def _bind(client, telegram, code, update_id, chat=777) -> str:
    payload = {"update_id": update_id, "message": {"text": f"/link {code}", "chat": {"id": chat}, "from": {}}}
    assert deliver(client, payload).status_code == 200
    return telegram.texts()[-1]
