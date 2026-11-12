"""Structured memory: bounded counts instead of a transcript, and behaviour that is measured.

Three properties matter: the summary never carries code or a full transcript, the
mentor receives the summary as untrusted data (so a prompt injection inside it has no
authority), and the behavioural profile is computed from recorded facts.
"""
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from test_auth import client, csrf
from test_learning import onboard, register

from app import ai_gateway, memory
from app.db.models import MentorConversation, MentorMessage, User
from app.db.session import get_db
from app.main import app

PATH = "/learning/lessons/variables-v1/chat"


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
        body = {"choices": [{"message": {"role": "assistant", "content": "Смотри на строку с присваиванием."},
                             "finish_reason": "stop"}]}
        return httpx.Response(200, json=body)

    monkeypatch.setattr(ai_gateway.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    return calls


def ask(client, text="Что делает присваивание?"):
    return client.post(PATH, headers={"X-CSRF-Token": csrf(client)},
                       json={"request_id": str(uuid4()), "message": text})


def test_summary_counts_and_flags_an_unanswered_question(client):
    register(client)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user_id = db.scalar(select(User.id))
        conversation = MentorConversation(user_id=user_id, lesson_id="variables-v1")
        db.add(conversation)
        db.flush()
        now = datetime.now(UTC)
        db.add(MentorMessage(conversation_id=conversation.id, role="user", status="completed",
                             content="Почему присваивание меняет переменную и как это работает",
                             created_at=now - timedelta(minutes=5)))
        db.add(MentorMessage(conversation_id=conversation.id, role="user", status="completed",
                             content="Присваивание перезаписывает значение переменной, верно?",
                             created_at=now))
        db.commit()
        summary = memory.interaction_summary(db, user_id=user_id, lesson_id="variables-v1")
    assert summary.questions == 2 and summary.answers == 0
    assert summary.awaiting_answer is True
    assert summary.last_question.startswith("Присваивание перезаписывает")
    assert "присваивание" in summary.topics


def test_summary_is_bounded_and_never_contains_code(client):
    register(client)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user_id = db.scalar(select(User.id))
        conversation = MentorConversation(user_id=user_id, lesson_id="variables-v1")
        db.add(conversation)
        db.flush()
        long_code = "def solve(payload):\n    return payload['secret']\n" * 20
        db.add(MentorMessage(conversation_id=conversation.id, role="user", status="completed", content=long_code))
        db.commit()
        summary = memory.interaction_summary(db, user_id=user_id, lesson_id="variables-v1")
    block = summary.prompt_block()
    assert len(block) < 400, block
    assert "return payload" not in block, "сводка не пересказывает код"
    assert len(summary.last_question) <= memory.MAX_QUESTION_CHARS


def test_profile_measures_preference_and_pass_rate(client):
    register(client)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        conversation = MentorConversation(user_id=user.id, lesson_id="variables-v1")
        db.add(conversation)
        db.flush()
        for mode in ("socratic", "socratic", "teach"):
            db.add(MentorMessage(conversation_id=conversation.id, role="assistant", status="completed",
                                 content="…", mode=mode))
        db.commit()
        profile = memory.behavioural_profile(db, user=user)
    assert profile["preferred_tutor_mode"] == "socratic"
    assert profile["mode_usage"] == {"socratic": 2, "teach": 1}
    assert profile["coding_runs"] == 0 and profile["coding_pass_rate"] == 0.0
    assert profile["pace"] == "inactive"


def test_mentor_receives_the_summary_as_untrusted_data(client, provider):
    register(client)
    onboard(client)
    ask(client, "Что такое переменная?")
    ask(client, "А как её изменить?")
    messages = provider[-1]["messages"]
    summary_messages = [item for item in messages if item["content"].startswith("Untrusted previous_dialogue")]
    assert summary_messages, [item["content"][:40] for item in messages]
    # The summary describes the dialogue that already happened: one question, one answer.
    assert "asked=1" in summary_messages[0]["content"]
    # The trusted system prompt is unchanged apart from the mode block.
    assert messages[0]["role"] == "system" and "previous_dialogue" not in messages[0]["content"]


def test_memory_endpoint_returns_profile_and_dialogue(client, provider):
    register(client)
    onboard(client)
    ask(client, "Что такое переменная?")
    body = client.get("/learning/lessons/variables-v1/chat").json()
    assert body, "история диалога доступна"
    memory_response = client.get("/me/memory?lesson_id=variables-v1")
    assert memory_response.status_code == 200, memory_response.text
    payload = memory_response.json()
    assert payload["dialogue"]["questions"] == 1
    assert payload["profile"]["preferred_tutor_mode"] == "teach"
    assert client.get("/me/memory").json()["dialogue"] is None
