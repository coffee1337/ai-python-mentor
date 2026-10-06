"""A novice can learn before being asked to demonstrate prior knowledge."""
import contextlib
import io
import pytest

from sqlalchemy import select

from app.assessment_content import MAX_QUESTIONS
from app.beginner_content import BEGINNER_LESSONS
from app.db.models import (AssessmentResponse, AssessmentRun, ExerciseVersion,
                           KnowledgeCheckSession, LessonCompletion, LessonSession,
                           SkillEvidence, User, UserSkill, UserMistake)
from app.db.session import get_db
from app.exercise_hints import _seed_exercise
from app.exercise_snapshots import snapshot_checks
from app.learning_content import LESSONS_BY_ID
from app.learning import CODING_INTERFACE_SKILLS
from app.main import app
from test_auth import client, csrf
from test_learning_plan import setup_user


def _db():
    return next(app.dependency_overrides[get_db]())


def test_novice_starts_with_explanation_without_diagnostic_or_fabricated_evidence(client):
    setup_user(client, "zero-programming@example.com")
    plan = client.get("/learning/plan").json()
    assert plan["status"] == "ready"
    assert plan["learning_mode"] == "starter"
    assert plan["assessment_optional"] is True
    assert plan["assessment_run_id"] is None and plan["skill_profile"] == []
    assert plan["recommended_lesson_id"] == "variables-v2"
    lesson = client.get("/learning/next").json()
    assert lesson["id"] == "variables-v2"
    assert lesson["prerequisites"] == []
    assert lesson["practice_submission_type"] == "guided_reading"
    assert {entry["term"] for entry in lesson["glossary"]} >= {"Программа", "Код", "Python", "Переменная", "Вывод"}
    assert len(lesson["example_walkthrough"]) == len(lesson["example"].splitlines())
    assert "answer" not in lesson and "checks" not in lesson
    assert client.get("/learning/exercises/variables-v2/coding-specification").status_code == 409
    with _db() as db:
        for model in (AssessmentRun, AssessmentResponse, SkillEvidence, UserSkill, LessonCompletion):
            assert db.scalar(select(model)) is None


def test_guided_lesson_checks_unlock_only_the_next_taught_topic(client):
    setup_user(client, "guided-progress@example.com")
    lesson = client.get("/learning/next").json()
    assert client.get("/learning/lessons/data-types-v2").status_code == 409
    questions = client.get(f"/learning/lessons/{lesson['id']}/knowledge-check").json()
    assert len(questions) == 2 and all("answer" not in question for question in questions)
    with _db() as db:
        version = _seed_exercise(db, lesson["id"])
        answers = {question["id"]: question["answer"] for question in snapshot_checks(version.content_snapshot)}
    result = client.post(f"/learning/lessons/{lesson['id']}/knowledge-check",
        headers={"X-CSRF-Token": csrf(client)}, json={"answers": answers})
    assert result.status_code == 201 and result.json()["passed"] is True
    assert client.get("/learning/next").json()["id"] == "data-types-v2"
    assert client.get("/learning/lessons/conditions-v2").status_code == 409
    plan = client.get("/learning/plan").json()
    assert plan["recommended_lesson_id"] == "data-types-v2"
    assert next(item for item in plan["items"] if item["lesson_id"] == lesson["id"])["status"] == "completed"
    with _db() as db:
        assert db.scalar(select(AssessmentRun)) is None
        evidence = db.scalars(select(SkillEvidence)).all()
        assert len(evidence) == 1 and evidence[0].source_type == "knowledge_check_attempt"


def test_historical_first_lesson_remains_exact_and_preserves_completion(client):
    setup_user(client, "historical-publication@example.com")
    with _db() as db:
        old = _seed_exercise(db, "variables-v1")
        original_snapshot = old.content_snapshot
        old_id = old.id
        db.commit()
    old_response = client.get("/learning/lessons/variables-v1").json()
    assert old_response["title"] == "Переменные и присваивание"
    assert old_response["example"] == "requests = 2\nrequests = requests + 1\nprint(requests)  # 3"
    completed = client.post("/learning/lessons/variables-v1/complete",
        headers={"X-CSRF-Token": csrf(client)}, json={"answer": "6"})
    assert completed.status_code == 200 and completed.json()["correct"] is True
    path = completed.json()["path"]
    assert next(item for item in path["lessons"] if item["id"] == "variables-v2")["status"] == "completed"
    assert path["next_lesson_id"] == "data-types-v2"
    with _db() as db:
        completion = db.scalar(select(LessonCompletion))
        assert completion.lesson_id == "variables-v1"
        assert completion.exercise_version_id == old_id
        assert db.get(ExerciseVersion, old_id).content_snapshot == original_snapshot
        assert db.scalar(select(SkillEvidence)) is None
        assert LESSONS_BY_ID["variables-v1"]["answer"] == "6"


@pytest.mark.parametrize("flow", ["lesson", "knowledge_check"])
def test_pending_historical_flow_resumes_instead_of_silently_switching_content(client, flow):
    setup_user(client, f"resume-{flow}@example.com")
    endpoint = "/learning/lessons/variables-v1"
    if flow == "knowledge_check":
        endpoint += "/knowledge-check"
    assert client.get(endpoint).status_code == 200
    with _db() as db:
        model = LessonSession if flow == "lesson" else KnowledgeCheckSession
        prior = db.scalar(select(model))
        version_id = prior.exercise_version_id
        snapshot = db.get(ExerciseVersion, version_id).content_snapshot
    assert client.get("/learning/plan").json()["resume_lesson_id"] == "variables-v1"
    resumed = client.get("/learning/next").json()
    assert resumed["id"] == "variables-v1"
    assert resumed["example"] == snapshot["lesson"]["example"]
    with _db() as db:
        lesson_session = db.scalar(select(LessonSession))
        assert lesson_session.exercise_version_id == version_id
    result = client.post("/learning/lessons/variables-v1/complete",
        headers={"X-CSRF-Token": csrf(client)}, json={"answer": "6"})
    assert result.status_code == 200 and result.json()["correct"] is True
    assert client.get("/learning/plan").json()["resume_lesson_id"] is None
    assert client.get("/learning/next").json()["id"] == "data-types-v2"


def test_all_introductory_examples_have_real_matching_output():
    for lesson in BEGINNER_LESSONS:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(lesson["example"], {})  # Reviewed authored code, never learner input.
        assert output.getvalue().rstrip("\n") == lesson["example_output"], lesson["id"]
        assert [step["line"] for step in lesson["example_walkthrough"]] == list(range(1, len(lesson["example"].splitlines()) + 1))


def test_untaught_function_interface_stays_hidden_on_later_early_topics(client):
    setup_user(client, "before-functions@example.com")
    # A credible assessment may open a later lesson, but it does not imply
    # that functions/dictionaries have also been learned.
    with _db() as db:
        user = db.scalar(select(User))
        db.add_all(UserSkill(user_id=user.id, skill_id=skill, evidence_count=1,
            independent_score=1, knowledge_score=1, practice_score=1)
            for skill in ("python.variables", "python.data_types", "python.conditionals"))
        db.commit()
    lesson = client.get("/learning/lessons/loops-v1")
    assert lesson.status_code == 200
    assert lesson.json()["practice_submission_type"] == "guided_reading"
    assert client.get("/learning/exercises/loops-v1/coding-specification").status_code == 409
    with _db() as db:
        user = db.scalar(select(User))
        db.add_all(UserSkill(user_id=user.id, skill_id=skill, evidence_count=1,
            independent_score=1, knowledge_score=1, practice_score=1)
            for skill in CODING_INTERFACE_SKILLS)
        db.commit()
    assert client.get("/learning/lessons/loops-v1").json()["practice_submission_type"] == "coding"
    specification = client.get("/learning/exercises/loops-v1/coding-specification")
    assert specification.status_code == 200
    assert "hidden" not in specification.text and "solution" not in specification.text


def test_unknown_diagnostic_questions_do_not_become_wrong_answers_or_evidence(client):
    setup_user(client, "unknown-diagnostic@example.com")
    state = client.get("/assessment").json()
    first_id = state["question"]["id"]
    assert client.post("/assessment/skip", json={"question_id": first_id}).status_code == 403
    assert client.post("/assessment/skip", headers={"X-CSRF-Token": csrf(client)},
        json={"question_id": first_id, "grade": 1}).status_code == 422
    seen = set()
    while not state["completed"]:
        question = state["question"]
        assert question["id"] not in seen
        seen.add(question["id"])
        result = client.post("/assessment/skip", headers={"X-CSRF-Token": csrf(client)},
            json={"question_id": question["id"]})
        assert result.status_code == 200
        state = result.json()
    assert len(seen) == MAX_QUESTIONS
    assert state["answered"] == 0 and state["skipped"] == MAX_QUESTIONS and state["score"] is None
    assert client.post("/assessment/skip", headers={"X-CSRF-Token": csrf(client)},
        json={"question_id": first_id}).status_code == 409
    assert client.get("/learning/plan").json()["learning_mode"] == "starter"
    assert client.get("/learning/next").json()["id"] == "variables-v2"
    with _db() as db:
        for model in (AssessmentResponse, SkillEvidence, UserSkill, UserMistake):
            assert db.scalar(select(model)) is None


def test_skip_and_real_answers_keep_evidence_and_grade_distinct(client):
    setup_user(client, "mixed-diagnostic@example.com")
    state = client.get("/assessment").json()
    question = state["question"]
    from content_helpers import authored_answer
    state = client.post("/assessment/answers", headers={"X-CSRF-Token": csrf(client)},
        json={"question_id": question["id"], "answer": authored_answer(question["id"])}).json()["state"]
    while not state["completed"]:
        state = client.post("/assessment/skip", headers={"X-CSRF-Token": csrf(client)},
            json={"question_id": state["question"]["id"]}).json()
    assert state["answered"] == 1 and state["skipped"] == MAX_QUESTIONS - 1
    assert state["score"] == 1
    with _db() as db:
        assert len(db.scalars(select(AssessmentResponse)).all()) == 1
        evidence = db.scalars(select(SkillEvidence)).all()
        assert len(evidence) == 1 and evidence[0].result_score == 1


def test_course_orientation_explains_actual_unconfigured_tutor(client, monkeypatch):
    for key in ("AI_GATEWAY_URL", "AI_GATEWAY_MODEL", "AI_GATEWAY_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert client.get("/learning/overview").status_code == 401
    setup_user(client, "orientation@example.com")
    overview = client.get("/learning/overview").json()
    assert overview["assessment_optional"] is True
    assert overview["mentor"]["status"] == "unconfigured"
    assert "пока не подключён" in overview["mentor"]["message"]
    assert "текущего урока" in overview["mentor"]["purpose"]
    assert len(overview["stages"]) == 3
    assert "API_KEY" not in str(overview)
