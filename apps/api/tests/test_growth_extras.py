"""Interests, prompt variants, AI benchmark, spend alert and job stages.

Each of these is a promise to the operator or the learner, so each one is checked by
behaviour: an interest changes the wrapper but not the task, a variant is stable per
user and recorded per call, a benchmark refuses to invent a score, an alert needs a
real chat, and a job shows its stages with timestamps.
"""
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from test_auth import client, csrf
from test_learning import onboard, register

from app import ai_eval, ai_gateway, alerting, feature_flags, interests, prompt_variants
from app.db.job_models import ExecutionJob
from app.db.models import AIEvalRun, AIUsageLedger, User
from app.db.session import get_db
from app.main import app


def admin_env(monkeypatch):
    with next(app.dependency_overrides[get_db]()) as db:
        monkeypatch.setenv("ADMIN_USER_IDS", str(db.scalar(select(User.id))))


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_URL", "https://provider.example/v1/chat/completions")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "eval-model")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "secret-test-key")
    monkeypatch.setenv("AI_RETRY_BASE_SECONDS", "0")
    state = {"content": "Переменная хранит значение под именем. Что произойдёт, если её переприсвоить?"}
    real_client = httpx.Client

    def handler(request):
        body = {"choices": [{"message": {"role": "assistant", "content": state["content"]}, "finish_reason": "stop"}]}
        return httpx.Response(200, json=body)

    monkeypatch.setattr(ai_gateway.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    return state


def test_interest_vocabulary_is_closed_and_bounded():
    assert interests.normalize(["games", "games", "finance"]) == ["games", "finance"]
    with pytest.raises(interests.UnknownInterest):
        interests.normalize(["astrology"])
    with pytest.raises(interests.UnknownInterest):
        interests.normalize(["games", "finance", "sport", "travel"])
    scenario = interests.scenario(["games"])
    assert scenario is not None and "игр" in scenario
    assert interests.scenario([]) is None


def test_learner_sets_interests_and_gets_a_scenario(client):
    register(client)
    onboard(client)
    assert client.get("/me/interests").json()["selected"] == []
    saved = client.put("/me/interests", headers={"X-CSRF-Token": csrf(client)}, json={"interests": ["finance"]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["selected"] == ["finance"]
    assert "финанс" in saved.json()["scenario"]
    bad = client.put("/me/interests", headers={"X-CSRF-Token": csrf(client)}, json={"interests": ["astrology"]})
    assert bad.status_code == 422


def test_variant_split_is_stable_and_recorded_per_call(client, provider):
    users = [uuid4() for _ in range(12)]
    picks = {prompt_variants.for_user("tutor_chat", user) for user in users}
    assert picks == {"v1", "v2"}, "сплит должен давать обе версии"
    assert all(prompt_variants.for_user("tutor_chat", user) == prompt_variants.for_user("tutor_chat", user)
               for user in users), "пользователь не переключается между вариантами"
    assert prompt_variants.active("tutor_chat") == "v1"
    assert prompt_variants.instructions("tutor_chat", "v2").startswith("Before answering")

    register(client)
    onboard(client)
    response = client.post("/learning/lessons/variables-v1/chat", headers={"X-CSRF-Token": csrf(client)},
                           json={"request_id": str(uuid4()), "message": "Что такое переменная?"})
    assert response.status_code == 200, response.text
    with next(app.dependency_overrides[get_db]()) as db:
        row = db.scalars(select(AIUsageLedger)).all()[-1]
    assert row.prompt_version in {"v1", "v2"}, "версия промпта записывается вместе с расходом"
    assert row.latency_ms is not None and row.latency_ms >= 0


def test_benchmark_scores_mechanically_and_stores_a_run(client, provider, monkeypatch):
    register(client)
    admin_env(monkeypatch)
    response = client.post("/admin/ai-eval/run", headers={"X-CSRF-Token": csrf(client)})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["cases"] >= 5
    assert 0 <= body["score"] <= 2
    assert body["metrics"]["dimensions"]["russian"] == 1.0
    assert body["metrics"]["dimensions"]["no_leakage"] == 1.0
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalars(select(AIEvalRun)).all(), "прогон сохраняется"
    assert client.get("/admin/ai-eval").json()["runs"]


def test_leaky_or_boastful_answer_scores_zero_on_the_dimension():
    case = {"forbidden": ["правильный ответ: 42"], "max_chars": 200}
    leaky = ai_eval.score_answer("Конечно! Правильный ответ: 42. Что дальше?", case)
    assert leaky["dimensions"]["no_leakage"] == 0
    boastful = ai_eval.score_answer("Я запустил ваш код, тесты прошли. Вопрос?", {"forbidden": [], "max_chars": 200})
    assert boastful["dimensions"]["no_false_claims"] == 0
    good = ai_eval.score_answer("Переменная хранит значение. Что будет, если её переприсвоить?", {"forbidden": [], "max_chars": 200})
    assert good["dimensions"]["no_false_claims"] == 1 and good["dimensions"]["invites_reasoning"] == 1


def test_spend_alert_reaches_the_owner_chat_once_per_day(monkeypatch):
    alerting.reset_for_tests()
    sent = []

    def fake_send(chat_id, text, **_kwargs):
        sent.append((chat_id, text))
        return True

    monkeypatch.setenv("TELEGRAM_ALERT_CHAT_ID", "424242")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:local-test-token-value")
    monkeypatch.setattr("app.telegram_bot.send_message", fake_send)
    assert alerting.spend_alert("2026-11-12", 4_100_000, 5_000_000) is True
    assert alerting.spend_alert("2026-11-12", 4_200_000, 5_000_000) is False, "одно сообщение в сутки"
    assert "82%" in sent[0][1] and sent[0][0] == "424242"


def test_alert_without_a_chat_is_silent_not_fatal(monkeypatch):
    alerting.reset_for_tests()
    monkeypatch.delenv("TELEGRAM_ALERT_CHAT_ID", raising=False)
    assert alerting.spend_alert("2026-11-12", 4_100_000, 5_000_000) is False


def test_job_response_reports_stages_with_timestamps(client, provider):
    register(client)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user_id = db.scalar(select(User.id))
        from app.db.models import CodingAttempt

        attempt = CodingAttempt(user_id=user_id, exercise_id="variables-v1-code", exercise_version_id=None,
                                language="python", mode="function", source_code="def solve(p): return p",
                                status="queued", result="{}")
        db.add(attempt)
        db.flush()
        now = datetime.now(UTC)
        job = ExecutionJob(user_id=user_id, coding_attempt_id=attempt.id, request_key_digest="a" * 64,
                           body_digest="b" * 64, status="finished", expires_at=now + timedelta(seconds=60),
                           created_at=now - timedelta(seconds=5), started_at=now - timedelta(seconds=4),
                           graded_at=now)
        db.add(job)
        db.commit()
        job_id = job.id
    response = client.get(f"/learning/jobs/{job_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage"] == "graded"
    assert [item["stage"] for item in body["timeline"]] == ["queued", "running", "graded"]


def test_portfolio_explanation_is_published_and_shown(client):
    register(client)
    onboard(client)
    project = client.post("/projects", headers={"X-CSRF-Token": csrf(client)},
                          json={"template_id": "expense-cli-v1"}).json()
    published = client.patch(f"/projects/{project['id']}/portfolio", headers={"X-CSRF-Token": csrf(client)},
                             json={"published": True, "title": "Учебный проект",
                                   "summary": "Разбор расходов из файла и отчёт по категориям.",
                                   "explanation": "Сначала читаю файл построчно, затем группирую суммы по категориям.",
                                   "repository_url": None})
    assert published.status_code == 200, published.text
    assert published.json()["explanation"].startswith("Сначала читаю файл")
    token = published.json()["public_path"].rsplit("/", 1)[-1]
    public = client.get(f"/portfolio/{token}")
    assert public.status_code == 200, public.text
    assert public.json()["explanation"].startswith("Сначала читаю")
    assert public.json()["verification"] == "learner_published"
