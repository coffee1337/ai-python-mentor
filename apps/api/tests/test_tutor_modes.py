"""Tutor modes: eight behaviours, explicit choice or server suggestion.

The mode is data, not a second prompt stack: it must reach the provider request,
be stored on the answer and be explainable to the learner.
"""
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from test_auth import client, csrf
from test_learning import onboard, register

from app import ai_gateway
from app import tutor_modes
from app.db.models import MentorMessage
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
    state = {"body": {"choices": [{"message": {"role": "assistant", "content": "Что делает присваивание?"},
                                   "finish_reason": "stop"}]}}
    real_client = httpx.Client

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=state["body"])

    monkeypatch.setattr(ai_gateway.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    return state, calls


def send(client, mode=None, message="Помоги понять присваивание"):
    payload = {"request_id": str(uuid4()), "message": message}
    if mode is not None:
        payload["mode"] = mode
    return client.post(PATH, headers={"X-CSRF-Token": csrf(client)}, json=payload)


def system_prompt(calls) -> str:
    return calls[-1]["messages"][0]["content"]


def test_catalogue_exposes_eight_modes(client):
    response = client.get("/learning/modes")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["default"] == "teach"
    ids = {mode["id"] for mode in body["modes"]}
    assert ids == {"teach", "socratic", "hint", "debug_coach", "review", "examiner", "interviewer", "project_mentor"}
    assert all(mode["title"] for mode in body["modes"]), "у каждого режима есть русское название"


def test_explicit_mode_reaches_the_provider_and_is_stored(client, provider):
    _, calls = provider
    register(client)
    onboard(client)
    response = send(client, mode="socratic")
    assert response.status_code == 200, response.text
    assert "Mode: socratic" in system_prompt(calls)
    assert "Ask one focused question" in system_prompt(calls)
    assert response.json()["mode"] == "socratic"
    assert response.json()["mode_reason"] == "explicit"
    with next(app.dependency_overrides[get_db]()) as db:
        stored = db.scalars(select(MentorMessage).where(MentorMessage.role == "assistant")).all()
    assert {row.mode for row in stored} == {"socratic"}


def test_unknown_mode_is_rejected(client, provider):
    register(client)
    onboard(client)
    assert send(client, mode="philosopher").status_code == 422


def test_default_mode_is_teach_without_signals(client, provider):
    _, calls = provider
    register(client)
    onboard(client)
    response = send(client)
    assert response.status_code == 200
    assert response.json()["mode"] == "teach"
    assert response.json()["mode_reason"] == "default"
    assert "Mode: teach" in system_prompt(calls)


def test_failed_runs_switch_the_mode_without_asking(client, provider):
    from app.db.models import CodingAttempt, User

    register(client)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        for _ in range(3):
            db.add(CodingAttempt(user_id=user.id, exercise_id="variables-v1", exercise_version_id=None,
                                 language="python", mode="function", source_code="def solve(p): pass",
                                 status="failed", result="{}"))
        db.commit()
    response = send(client)
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "debug_coach"
    assert response.json()["mode_reason"] == "failed_runs"


def test_repeated_confusion_switches_to_explanation(client, provider):
    register(client)
    onboard(client)
    for _ in range(2):
        assert send(client, message="Не понимаю, что тут происходит").status_code == 200
    response = send(client, message="Не понимаю, что тут происходит")
    assert response.json()["mode_reason"] == "repeated_confusion"


def test_every_mode_keeps_the_trusted_base_rules():
    from app.mentor_prompts import SYSTEM_PROMPT

    for mode in tutor_modes.MODES:
        prompt = tutor_modes.system_prompt(SYSTEM_PROMPT, mode)
        # The mode block is additive: the privacy and scope rules stay verbatim.
        assert prompt.startswith(SYSTEM_PROMPT), mode
        assert "Never claim mastery" in prompt, mode
        assert len(tutor_modes.MODES[mode]["rules"]) < 400, mode
