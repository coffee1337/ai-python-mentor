"""Rubric reviews: the model grades, the server scores.

The tests fix three properties the learner depends on: weights follow the level,
a model answer that claims a total cannot change the result, and a malformed answer
is refused instead of shown with guessed numbers.
"""
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from test_auth import client, csrf
from test_learning import onboard, register

from app import ai_gateway, rubric
from app.db.models import CodeReview, CodingAttempt, User
from app.db.session import get_db
from app.main import app

PATH = "/learning/exercises/variables-v1-code/review"
GOOD = {"criteria": {"correctness": 2, "readability": 1, "edge_cases": 1, "testing": 0, "complexity": 1, "style": 1},
        "notes": {"correctness": "Решает задачу.", "testing": "Тестов нет."}}


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_URL", "https://provider.example/v1/chat/completions")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "review-model")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "secret-test-key")
    monkeypatch.setenv("AI_RETRY_BASE_SECONDS", "0")
    state = {"content": json.dumps(GOOD), "status": 200, "calls": []}
    real_client = httpx.Client

    def handler(request):
        state["calls"].append(json.loads(request.content))
        body = {"choices": [{"message": {"role": "assistant", "content": state["content"]}, "finish_reason": "stop"}]}
        return httpx.Response(state["status"], json=body)

    monkeypatch.setattr(ai_gateway.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    return state


def seed_submission(exercise_id="variables-v1-code", source="def solve(p):\n    return p\n"):
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        db.add(CodingAttempt(user_id=user.id, exercise_id=exercise_id, exercise_version_id=None,
                             language="python", mode="function", source_code=source, status="finished", result="{}"))
        db.commit()


def submit(client):
    return client.post(PATH, headers={"X-CSRF-Token": csrf(client)})


def test_weights_follow_the_level_and_sum_to_one_hundred():
    for level in ("beginner", "intermediate", "advanced"):
        weights = rubric.weights_for(level)
        assert sum(weights.values()) == 100, level
    assert rubric.weights_for("beginner")["correctness"] > rubric.weights_for("advanced")["correctness"]
    assert rubric.weights_for("advanced")["testing"] > rubric.weights_for("beginner")["testing"]
    assert rubric.weights_for(None) == rubric.BASE_WEIGHTS, "неизвестный уровень не ломает рубрику"


def test_model_total_is_ignored_and_score_is_computed_here(provider):
    provider["content"] = json.dumps({**GOOD, "total": 100, "score": 100})
    grades, _ = rubric.parse(provider["content"])
    expected = rubric.score(grades, rubric.BASE_WEIGHTS)
    result = rubric.review(provider["content"], "intermediate")
    assert result.score == expected != 100


def test_malformed_answer_is_refused():
    for bad in (
        "не json",
        json.dumps({"criteria": {**GOOD["criteria"], "correctness": 5}}),
        json.dumps({"criteria": {**GOOD["criteria"], "correctness": True}}),
        json.dumps({"criteria": {k: v for k, v in GOOD["criteria"].items() if k != "style"}}),
        json.dumps({"criteria": {**GOOD["criteria"], "invented": 1}}),
    ):
        with pytest.raises(rubric.InvalidReview):
            rubric.parse(bad)


def test_endpoint_scores_by_level_and_stores_the_review(client, provider):
    register(client)
    onboard(client)
    seed_submission()
    response = submit(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["model"] == "review-model"
    assert body["score"] == rubric.score(rubric.parse(provider["content"])[0], rubric.weights_for(body["level"]))
    assert {item["id"] for item in body["criteria"]} == set(rubric.CRITERIA)
    assert all(item["weight"] >= 0 for item in body["criteria"])
    with next(app.dependency_overrides[get_db]()) as db:
        rows = db.scalars(select(CodeReview)).all()
    assert len(rows) == 1 and rows[0].score == body["score"]

    history = client.get("/learning/exercises/variables-v1-code/reviews")
    assert history.status_code == 200 and len(history.json()) == 1


def test_bad_model_answer_is_a_502_and_nothing_is_stored(client, provider):
    provider["content"] = "Извините, не могу оценить."
    register(client)
    onboard(client)
    seed_submission()
    response = submit(client)
    assert response.status_code == 502, response.text
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalars(select(CodeReview)).all() == []


def test_review_needs_a_submission_and_an_account(client, provider):
    assert submit(client).status_code == 401
    register(client)
    onboard(client)
    assert submit(client).status_code == 404, "ревью не выдумывает код, которого нет"


def test_gateway_failure_is_a_503_not_a_zero_score(client, provider, monkeypatch):
    provider["status"] = 503
    register(client)
    onboard(client)
    seed_submission()
    assert submit(client).status_code == 503


def test_rubric_endpoint_lists_all_weights(client):
    body = client.get("/learning/rubric").json()
    assert {item["id"] for item in body["criteria"]} == set(rubric.CRITERIA)
    assert set(body["levels"]) == {"beginner", "intermediate", "advanced"}
    assert body["pass_threshold"] == rubric.PASS_THRESHOLD
