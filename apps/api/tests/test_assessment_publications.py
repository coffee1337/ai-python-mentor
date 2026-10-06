import contextlib
import io
import json
import pytest
from sqlalchemy import select

from app.assessment_content import HISTORICAL_QUESTIONS, QUESTIONS, QUESTIONS_BY_ID
from app.db.models import AssessmentResponse, AssessmentRun, ExerciseVersion, User
from app.db.session import get_db
from app.exercise_hints import _seed_exercise
from app.main import app
from test_auth import client, csrf
from test_learning_plan import setup_user


@pytest.mark.parametrize("old_id,new_id", [
    ("conditions-chain-v1", "conditions-chain-formatted-v1"),
    ("loops-accumulate-v1", "loops-accumulate-formatted-v1"),
])
def test_formatted_diagnostic_examples_execute_and_old_publication_is_retained(old_id, new_id):
    old = QUESTIONS_BY_ID[old_id]
    current = QUESTIONS_BY_ID[new_id]
    assert old in HISTORICAL_QUESTIONS and old not in QUESTIONS
    assert current in QUESTIONS and old["id"] != current["id"]
    assert "code" not in old and ";" in old["prompt"]
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(current["code"], {})  # Only reviewed repository-owned Python.
    assert output.getvalue().strip() == current["answer"]
    assert current["choices"] == old["choices"]
    assert current["difficulty"] == old["difficulty"]


@pytest.mark.parametrize("old_id", ["conditions-chain-v1", "loops-accumulate-v1"])
def test_existing_old_assessment_question_is_shown_and_graded_by_its_exact_snapshot(client, old_id):
    setup_user(client, f"old-{old_id}@example.com")
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        old_version = _seed_exercise(db, old_id)
        snapshot = old_version.content_snapshot
        version_id = old_version.id
        db.add(AssessmentRun(user_id=user.id, current_question_id=old_id,
            current_exercise_version_id=version_id, asked_question_ids=json.dumps([old_id])))
        db.commit()
    state = client.get("/assessment").json()
    assert state["question"]["id"] == old_id
    assert state["question"]["prompt"] == snapshot["assessment"]["prompt"]
    assert state["question"]["code"] is None
    assert "answer" not in state["question"]
    graded = client.post("/assessment/answers", headers={"X-CSRF-Token": csrf(client)},
        json={"question_id": old_id, "answer": snapshot["assessment"]["answer"]})
    assert graded.status_code == 200 and graded.json()["correct"] is True
    with next(app.dependency_overrides[get_db]()) as db:
        response = db.scalar(select(AssessmentResponse))
        assert response.question_id == old_id and response.exercise_version_id == version_id
        assert db.get(ExerciseVersion, version_id).content_snapshot == snapshot
