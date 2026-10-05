from content_helpers import authored_answer, authored_wrong_answer
from sqlalchemy import select
from app.db.models import AssessmentResponse, AssessmentRun, ExerciseVersion, HintReveal, SkillEvidence
from app.db.session import get_db
from app.main import app
from app.assessment_content import QUESTIONS
from app.assessment_content import MAX_QUESTIONS
from app.learning_content import EXERCISE_HINT_LADDERS
from test_auth import client, csrf
from content_helpers import enable_choice_feedback

def setup_user(c, email="assessment@example.com", level="beginner"):
    from app.auth import _attempts
    _attempts.clear()
    assert c.post("/auth/register", json={"email":email,"password":"safe-password"}).status_code == 201
    assert c.post("/onboarding", headers={"X-CSRF-Token":csrf(c)}, json={"experience_level":level,"target_role":"Python Backend","weekly_minutes":180}).status_code == 200

def test_assessment_requires_auth_onboarding_and_csrf(client):
    assert client.get("/assessment").status_code == 401
    setup_user(client)
    first=client.get("/assessment")
    assert first.status_code == 200 and first.json()["question"]["id"] == "variables-v1"
    q=first.json()["question"]
    assert '"answer":' not in first.text
    assert client.post("/assessment/answers", json={"question_id":q["id"],"answer":"6"}).status_code == 403
    assert client.post("/assessment/answers", headers={"X-CSRF-Token":csrf(client)}, json={"question_id":q["id"],"answer":"invalid"}).status_code == 422

def test_assessment_adapts_persists_and_completes(client):
    setup_user(client)
    headers={"X-CSRF-Token":csrf(client)}
    state=client.get("/assessment").json(); q=state["question"]
    response=client.post("/assessment/answers",headers=headers,json={"question_id":q["id"],"answer":"6"})
    assert response.json()["correct"] is True
    assert response.json()["state"]["question"]["difficulty"] > q["difficulty"]
    q=response.json()["state"]["question"]
    for _ in range(MAX_QUESTIONS-1):
        response=client.post("/assessment/answers",headers=headers,json={"question_id":q["id"],"answer":authored_answer(q["id"])})
        if response.json()["state"]["question"] is not None: q=response.json()["state"]["question"]
    assert response.json()["state"]["completed"] is True
    assert client.get("/assessment").json()["status"] == "completed"
    with next(app.dependency_overrides[get_db]()) as db:
        run=db.scalar(select(AssessmentRun))
        rows=db.scalars(select(AssessmentResponse).where(AssessmentResponse.run_id==run.id)).all()
        assert run.status == "completed" and len(rows) == MAX_QUESTIONS and all(row.run_id == run.id for row in rows)
        assert any(row.exercise_version_id is not None for row in rows)

def test_assessment_ownership_and_stale_question(client):
    setup_user(client)
    first=client.get("/assessment").json(); headers={"X-CSRF-Token":csrf(client)}
    assert client.post("/assessment/answers",headers=headers,json={"question_id":"types-v1","answer":"float"}).status_code == 409
    client.post("/auth/logout",headers=headers)
    setup_user(client,"second-assessment@example.com")
    second=client.get("/assessment").json()
    assert second["question"]["id"] == "variables-v1"
    assert client.post("/assessment/answers",headers={"X-CSRF-Token":csrf(client)},json={"question_id":first["question"]["id"],"answer":"6"}).status_code == 200


def test_hint_revealed_after_assessment_response_does_not_assist_that_response(client):
    setup_user(client, "assessment-hint-timing@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    state = client.get("/assessment").json()
    first = state["question"]
    assert first["id"] == "variables-v1"

    state = client.post(
        "/assessment/answers",
        headers=headers,
        json={"question_id": first["id"], "answer": authored_answer(first["id"])},
    ).json()["state"]
    assert client.post(
        "/learning/exercises/variables-v1/hints",
        headers={**headers, "Idempotency-Key": "after-assessment-response"},
        json={"level": 1},
    ).status_code == 200

    for _ in range(MAX_QUESTIONS - 1):
        question = state["question"]
        state = client.post(
            "/assessment/answers",
            headers=headers,
            json={"question_id": question["id"], "answer": authored_answer(question["id"])},
        ).json()["state"]
    assert state["completed"] is True

    with next(app.dependency_overrides[get_db]()) as db:
        response = db.scalar(
            select(AssessmentResponse).where(AssessmentResponse.question_id == "variables-v1")
        )
        reveal = db.scalar(select(HintReveal))
        evidence = db.scalar(
            select(SkillEvidence).where(
                SkillEvidence.source_type == "assessment_response",
                SkillEvidence.source_id == str(response.id),
            )
        )
        assert response.created_at < reveal.revealed_at
        assert evidence.assisted is False
        assert evidence.hint_count == 0


def test_assessment_uses_bound_snapshot_after_authored_content_changes(client, monkeypatch):
    setup_user(client, "assessment-snapshot@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    first = client.get("/assessment").json()["question"]
    assert first["id"] == "variables-v1"

    original = EXERCISE_HINT_LADDERS["variables-v1"]["version"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original + 1)
    enable_choice_feedback(monkeypatch, "variables-v1", prefix="assessment-publication")
    monkeypatch.setattr(
        "app.assessment.QUESTIONS",
        tuple(
            {**question, "prompt": "MUTATED", "choices": ["MUTATED"], "answer": "MUTATED"}
            if question["id"] == "variables-v1"
            else question
            for question in QUESTIONS
        ),
    )
    try:
        state = client.get("/assessment")
        assert state.status_code == 200
        assert state.json()["question"]["prompt"] == first["prompt"]
        assert state.json()["question"]["choices"] == first["choices"]
        answered = client.post(
            "/assessment/answers",
            headers=headers,
            json={"question_id": first["id"], "answer": "6"},
        )
        assert answered.status_code == 200
        with next(app.dependency_overrides[get_db]()) as db:
            response = db.scalar(
                select(AssessmentResponse).where(AssessmentResponse.question_id == first["id"])
            )
            version = db.get(ExerciseVersion, response.exercise_version_id)
            assert version is not None
            assert version.content_snapshot["assessment"]["prompt"] == first["prompt"]
            assert set(version.content_snapshot["assessment"]["choices"]) == set(first["choices"])
    finally:
        monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original)


def test_assessment_binds_next_hinted_question_before_returning_it(client):
    setup_user(client, "assessment-next-snapshot@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    first = client.get("/assessment").json()["question"]
    response = client.post(
        "/assessment/answers",
        headers=headers,
        json={"question_id": first["id"], "answer": "6"},
    )
    assert response.status_code == 200
    next_question = response.json()["state"]["question"]
    # A correct answer steps one authored difficulty slot up.
    assert next_question["difficulty"] > first["difficulty"]
    assert next_question["skill_id"] != first["skill_id"]
    with next(app.dependency_overrides[get_db]()) as db:
        run = db.scalar(select(AssessmentRun))
        version = db.get(ExerciseVersion, run.current_exercise_version_id)
        assert version is not None
        assert version.exercise_id == next_question["id"]


def test_assessment_binds_non_hint_question_snapshot(client, monkeypatch):
    setup_user(client, "assessment-non-hint-snapshot@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    first = client.get("/assessment").json()["question"]
    assert first["id"] == "variables-v1"

    state = client.post(
        "/assessment/answers",
        headers=headers,
        json={"question_id": first["id"], "answer": "4"},
    ).json()["state"]
    # A wrong answer steps one authored difficulty slot down and never repeats
    # the skill that was just asked.
    next_question = state["question"]
    assert next_question["id"] == "data-types-cast-v1"
    assert next_question["difficulty"] <= first["difficulty"]
    assert next_question["skill_id"] != first["skill_id"]

    with next(app.dependency_overrides[get_db]()) as db:
        run = db.scalar(select(AssessmentRun).where(AssessmentRun.status == "in_progress"))
        version = db.get(ExerciseVersion, run.current_exercise_version_id)
        assert version is not None
        assert version.exercise_id == "data-types-cast-v1"
        assert version.content_snapshot["assessment"]["prompt"] == "Что вернёт `type(3.14).__name__`?"
        assert version.content_snapshot["hints"] == []

    monkeypatch.setattr(
        "app.assessment.QUESTIONS",
        tuple(
            {**question, "prompt": "MUTATED", "choices": ["MUTATED"], "answer": "MUTATED"}
            if question["id"] == "data-types-cast-v1"
            else question
            for question in QUESTIONS
        ),
    )
    try:
        current = client.get("/assessment")
        assert current.status_code == 200
        assert current.json()["question"]["prompt"] == "Что вернёт `type(3.14).__name__`?"
        assert client.post(
            "/assessment/answers",
            headers=headers,
            json={"question_id": "data-types-cast-v1", "answer": "float"},
        ).status_code == 200
    finally:
        monkeypatch.undo()


def test_assessment_rejects_legacy_in_progress_run_without_snapshot(client):
    setup_user(client, "assessment-null-version@example.com")
    first = client.get("/assessment").json()["question"]
    with next(app.dependency_overrides[get_db]()) as db:
        run = db.scalar(select(AssessmentRun))
        run.current_exercise_version_id = None
        db.commit()
    assert client.get("/assessment").status_code == 409
    assert client.post(
        "/assessment/answers",
        headers={"X-CSRF-Token": csrf(client)},
        json={"question_id": first["id"], "answer": authored_answer(first["id"])},
    ).status_code == 409
