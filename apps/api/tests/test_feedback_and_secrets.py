"""Feedback, confidence and secret scanning: signals that must stay honest.

Feedback is one vote per answer and belongs to the owner of the dialogue. Confidence
is compared with the real result and named plainly. A pasted secret never reaches
storage, the model or the log.
"""
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from test_auth import client, csrf
from test_learning import onboard, register

from app import ai_gateway, secret_scan
from app.db.models import AIFeedback, ConfidenceReport, MentorConversation, MentorMessage, User
from app.db.session import get_db
from app.main import app

CHAT = "/learning/lessons/variables-v1/chat"


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_URL", "https://provider.example/v1/chat/completions")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "test-model")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "secret-test-key")
    monkeypatch.setenv("AI_RETRY_BASE_SECONDS", "0")
    calls = []
    real_client = httpx.Client

    def handler(request):
        calls.append(json.loads(request.content))
        body = {"choices": [{"message": {"role": "assistant", "content": "Начните с присваивания."},
                             "finish_reason": "stop"}]}
        return httpx.Response(200, json=body)

    monkeypatch.setattr(ai_gateway.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    return calls


def ask(client, text="Что делает присваивание?"):
    return client.post(CHAT, headers={"X-CSRF-Token": csrf(client)},
                       json={"request_id": str(uuid4()), "message": text})


def admin_env(monkeypatch):
    with next(app.dependency_overrides[get_db]()) as db:
        monkeypatch.setenv("ADMIN_USER_IDS", str(db.scalar(select(User.id))))


def test_feedback_is_one_vote_and_can_be_changed(client, provider):
    register(client)
    onboard(client)
    answer = ask(client).json()
    path = f"/learning/mentor/messages/{answer['id']}/feedback"
    first = client.post(path, headers={"X-CSRF-Token": csrf(client)}, json={"helpful": False, "reason": "Слишком общо"})
    assert first.status_code == 201, first.text
    again = client.post(path, headers={"X-CSRF-Token": csrf(client)}, json={"helpful": True})
    assert again.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        rows = db.scalars(select(AIFeedback)).all()
    assert len(rows) == 1, "одна оценка на ответ, а не история голосов"
    assert rows[0].helpful is True and rows[0].reason is None
    assert client.get(path).json()["helpful"] is True


def test_feedback_on_someone_elses_answer_is_not_found(client, provider):
    register(client)
    onboard(client)
    ask(client)
    with next(app.dependency_overrides[get_db]()) as db:
        mine = db.scalar(select(MentorMessage).where(MentorMessage.role == "assistant"))
        stranger = User(email="other@example.com", password_hash="x", is_active=True)
        db.add(stranger)
        db.flush()
        conversation = MentorConversation(user_id=stranger.id, lesson_id="variables-v1")
        db.add(conversation)
        db.flush()
        foreign = MentorMessage(conversation_id=conversation.id, role="assistant", content="…", status="completed")
        db.add(foreign)
        db.commit()
        foreign_id, mine_id = foreign.id, mine.id
    assert client.post(f"/learning/mentor/messages/{foreign_id}/feedback",
                       headers={"X-CSRF-Token": csrf(client)}, json={"helpful": True}).status_code == 404
    assert client.post(f"/learning/mentor/messages/{mine_id}/feedback",
                       headers={"X-CSRF-Token": csrf(client)}, json={"helpful": True}).status_code == 201


def test_feedback_summary_is_admin_only_and_aggregates_reasons(client, provider, monkeypatch):
    register(client)
    onboard(client)
    answer = ask(client).json()
    client.post(f"/learning/mentor/messages/{answer['id']}/feedback",
                headers={"X-CSRF-Token": csrf(client)}, json={"helpful": False, "reason": "Не по теме"})
    assert client.get("/admin/analytics/feedback").status_code == 403
    admin_env(monkeypatch)
    body = client.get("/admin/analytics/feedback").json()
    assert body["not_helpful"] == 1 and body["helpful"] == 0
    assert body["helpful_rate"] == 0.0
    assert body["reasons"][0]["reason"] == "Не по теме"


def test_confidence_is_compared_with_the_real_result(client, provider):
    register(client)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user_id = db.scalar(select(User.id))
    assert client.post("/learning/lessons/variables-v1/confidence",
                       headers={"X-CSRF-Token": csrf(client)}, json={"confidence": 5}).status_code == 201
    body = client.get("/learning/lessons/variables-v1/confidence").json()
    assert body["confidence"] == 5 and body["verdict"] == "pending", "проверки ещё не было"

    from app.db.models import KnowledgeCheckAttempt

    with next(app.dependency_overrides[get_db]()) as db:
        db.add(KnowledgeCheckAttempt(user_id=user_id, exercise_version_id=None, lesson_id="variables-v1",
                                     skill_id="python.variables", score=0.25, passed=False))
        db.commit()
    body = client.get("/learning/lessons/variables-v1/confidence").json()
    assert body["verdict"] == "overconfident"
    assert "разобрать тему" in body["message"]


def test_confidence_range_is_enforced(client):
    register(client)
    onboard(client)
    for value in (0, 6):
        response = client.post("/learning/lessons/variables-v1/confidence",
                               headers={"X-CSRF-Token": csrf(client)}, json={"confidence": value})
        assert response.status_code == 422


def test_secret_patterns_are_detected_and_masked():
    samples = {
        "openai_key": "key = 'sk-abcdefghijklmnopqrstuvwxyz012345'",
        "github_token": "token = 'ghp_" + "a" * 36 + "'",
        "aws_access_key": "AKIA" + "B" * 16,
        "private_key": "-----BEGIN RSA PRIVATE KEY-----",
        "connection_string": "postgresql://user:supersecret@db:5432/app",
        "dotenv_secret": "DATABASE_PASSWORD=verysecretvalue",
    }
    for kind, sample in samples.items():
        result = secret_scan.scan(sample)
        assert not result.clean, kind
        assert kind in result.kinds(), (kind, result.kinds())
        assert "supersecret" not in " ".join(finding.excerpt for finding in result.findings)
    assert secret_scan.scan("def solve(payload):\n    return payload['start']").clean


def test_submission_with_a_secret_is_refused(client):
    register(client)
    onboard(client)
    response = client.post("/learning/exercises/variables-v1-code/jobs",
                           headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": f"k-{uuid4()}"},
                           json={"language": "python", "mode": "function",
                                 "source_code": "import os\nKEY = 'sk-abcdefghijklmnopqrstuvwxyz012345'\ndef solve(p): return 1\n"})
    assert response.status_code == 422, response.text
    assert "секрет" in response.json()["detail"].lower()


def test_mentor_refuses_a_pasted_key(client, provider):
    register(client)
    onboard(client)
    response = ask(client, "Вот мой ключ sk-abcdefghijklmnopqrstuvwxyz012345, почему не работает?")
    assert response.status_code == 422
    assert "секрет" in response.json()["detail"].lower()
    assert provider == [], "сообщение с секретом не уходит провайдеру"
