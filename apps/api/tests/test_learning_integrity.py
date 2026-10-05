from uuid import UUID
from sqlalchemy import select
from app.assessment_content import QUESTIONS
from app.choice_order import ordered_choices
from app.db.models import ExerciseVersion, LessonSession, SkillEvidence, User
from app.db.session import get_db
from app.exercise_hints import _seed_exercise
from app.learning import LessonResponse, _lesson_response
from app.main import app
from test_auth import client, csrf


def register(c, email="integrity@example.com"):
    assert c.post("/auth/register", json={"email": email, "password": "safe-password"}).status_code == 201
    assert c.post("/onboarding", headers={"X-CSRF-Token": csrf(c)}, json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180,
    }).status_code == 200


def test_correct_answer_position_varies_without_mutating_authored_content():
    question = QUESTIONS[0]
    original = list(question["choices"])
    positions = {ordered_choices(original, session_id=UUID(int=n), question_id=question["id"]).index(question["answer"]) for n in range(1, 100)}
    assert positions == set(range(len(original)))
    assert question["choices"] == original


def test_assessment_reload_stable_and_grades_answer_string(client):
    register(client)
    first = client.get("/assessment").json()["question"]
    assert client.get("/assessment").json()["question"] == first
    answer = next(q["answer"] for q in QUESTIONS if q["id"] == first["id"])
    response = client.post("/assessment/answers", headers={"X-CSRF-Token": csrf(client)}, json={"question_id": first["id"], "answer": answer})
    assert response.status_code == 200 and response.json()["correct"]
    assert '"answer"' not in response.text


def test_legacy_checkpoint_response_adapts_without_rewriting_snapshot(client):
    register(client)
    with next(app.dependency_overrides[get_db]()) as db:
        version = _seed_exercise(db, "imports-v1", seed_hints=False)
        original = version.content_snapshot
        assert isinstance(original["lesson"]["checkpoint"]["choices"], str)
        response = LessonResponse.model_validate(_lesson_response(version, "imports-v1", UUID(int=1)))
        assert len(response.checkpoint.choices) == 1
        assert version.content_snapshot == original


def test_hint_history_restores_reveals_and_is_owner_scoped(client):
    register(client)
    path = "/learning/exercises/variables-v1/hints"
    initial = client.get(path)
    assert initial.status_code == 200
    assert initial.json()["revealed"] == [] and initial.json()["next_level"] == 1
    reveal = client.post(path, headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "restore-hint-one"}, json={"level": 1})
    assert reveal.status_code == 200
    state = client.get(path).json()
    assert state["revealed"] == [reveal.json()] and state["next_level"] == 2
    assert '"solution"' not in client.get(path).text
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    register(client, "other-integrity@example.com")
    assert client.get(path).json()["revealed"] == []


def test_written_practice_persists_once_without_mastery_credit(client):
    register(client)
    endpoint = "/learning/lessons/variables-v1/reflections"
    assert client.post(endpoint, json={"text": "Разбор"}, headers={"Idempotency-Key": "reflection-once"}).status_code == 403
    headers = {"X-CSRF-Token": csrf(client), "Idempotency-Key": "reflection-once"}
    body = {"text": "Переменная хранит текущее значение, повторное присваивание заменяет его."}
    result = client.post(endpoint, headers=headers, json=body)
    assert result.status_code == 201
    assert client.post(endpoint, headers=headers, json=body).json() == result.json()
    assert client.post(endpoint, headers=headers, json={"text": "Иной ответ"}).status_code == 409
    assert len(client.get(endpoint).json()) == 1
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(SkillEvidence)) is None
        session = db.scalar(select(LessonSession))
        assert db.get(ExerciseVersion, session.exercise_version_id).exercise_id == "variables-v1"
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    register(client, "other-reflection@example.com")
    assert client.get(endpoint).json() == []
