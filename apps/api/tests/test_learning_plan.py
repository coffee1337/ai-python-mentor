from content_helpers import authored_answer, authored_wrong_answer
from sqlalchemy import select
from datetime import datetime, timedelta, timezone

from app.db.models import AssessmentRun, LessonCompletion, LearningPlan, LearningPlanItem, User, UserSkill
from app.db.session import get_db
from app.assessment_content import MAX_QUESTIONS
from app.learning_content import LESSONS
from app.main import app
from test_auth import client, csrf

def setup_user(c, email="plan@example.com"):
    assert c.post("/auth/register", json={"email":email,"password":"safe-password"}).status_code == 201
    assert c.post("/onboarding", headers={"X-CSRF-Token":csrf(c)}, json={"experience_level":"beginner","target_role":"Python Backend","weekly_minutes":180}).status_code == 200

def finish_assessment(c, answers=None):
    headers={"X-CSRF-Token":csrf(c)}; state=c.get("/assessment").json(); answers=answers or []
    for index in range(MAX_QUESTIONS):
        q=state["question"]; value=answers[index] if index < len(answers) and answers[index] in q["choices"] else authored_answer(q["id"])
        state=c.post("/assessment/answers",headers=headers,json={"question_id":q["id"],"answer":value}).json()["state"]
    return state

def test_plan_is_available_before_optional_assessment_and_is_owned(client):
    assert client.get("/learning/plan").status_code == 401
    setup_user(client)
    pending=client.get("/learning/plan")
    assert pending.status_code == 200 and pending.json()["status"] == "ready"
    assert pending.json()["learning_mode"] == "starter"
    assert pending.json()["assessment_run_id"] is None
    finish_assessment(client, ["6", "float", "adult", "3"])
    plan=client.get("/learning/plan").json()
    assert plan["status"] == "ready"
    # The first recommendation is a prerequisite-ready course root; the bank now
    # samples several early skills; the active replacements preserve readiness.
    assert plan["recommended_lesson_id"] in {"variables-v2", "data-types-v2"}
    assert {item["lesson_id"] for item in plan["items"] if item["status"] != "locked"} >= {"variables-v2", "data-types-v2"}
    assert {item["lesson_id"] for item in plan["items"]} >= {"variables-v2", "conditions-v2"}
    assert all(
        item["status"] != "recommended"
        or item["lesson_id"] == plan["recommended_lesson_id"]
        for item in plan["items"]
    )
    assert client.get("/learning/path").json()["next_lesson_id"] == plan["recommended_lesson_id"]
    assert plan["skill_profile"]
    client.post("/auth/logout",headers={"X-CSRF-Token":csrf(client)})
    setup_user(client,"other-plan@example.com")
    assert client.get("/learning/plan").json()["learning_mode"] == "starter"

def _correct_choice(exercise_id, index):
    """Resolve the authored answer key from the immutable exercise snapshot.

    The learner-facing API never returns the answer, so a test that needs a
    fully correct attempt reads the published snapshot instead.
    """
    from app.exercise_hints import _seed_exercise
    from app.exercise_snapshots import snapshot_checks

    with next(app.dependency_overrides[get_db]()) as db:
        version = _seed_exercise(db, exercise_id)
        return snapshot_checks(version.content_snapshot)[index]["answer"]


def test_plan_recommendation_follows_progress_and_reassessment_updates_version(client):
    setup_user(client,"versioned-plan@example.com"); finish_assessment(client,["4","int","minor","2"])
    first=client.get("/learning/plan").json(); first_version=first["version"]; first_lesson=first["recommended_lesson_id"]
    with next(app.dependency_overrides[get_db]()) as db:
        baseline_runs = len(db.scalars(select(AssessmentRun)).all())

    # Advance the learner through the service's own grading path.
    questions=client.get(f"/learning/lessons/{first_lesson}/knowledge-check").json()
    answers={
        question["id"]: _correct_choice(first_lesson, index)
        for index, question in enumerate(questions)
    }
    graded=client.post(
        f"/learning/lessons/{first_lesson}/knowledge-check",
        headers={"X-CSRF-Token":csrf(client)},
        json={"answers":answers},
    )
    assert graded.status_code == 201 and graded.json()["passed"] is True
    assert client.get("/learning/plan").json()["recommended_lesson_id"] != first_lesson

    assert client.post("/assessment/restart",headers={"X-CSRF-Token":csrf(client)}).status_code == 200
    finish_assessment(client,["6","float","adult","3"])
    second=client.get("/learning/plan").json()
    # Passing the knowledge check also refreshes the plan, so the reassessment
    # is the next version, not necessarily first_version + 1.
    assert second["version"] > first_version
    completed=next(item for item in second["items"] if item["lesson_id"]==first_lesson)
    assert completed["status"] == "completed"
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(LearningPlan)).version == second["version"]
        assert len(db.scalars(select(LearningPlanItem)).all()) == len(LESSONS)
        # One initial run plus one restart; the graded check does not add a run.
        assert len(db.scalars(select(AssessmentRun)).all()) == baseline_runs + 1


def test_plan_appends_due_review_only_for_completed_lessons(client):
    setup_user(client, "plan-review@example.com")
    now = datetime.now(timezone.utc)
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        run = AssessmentRun(
            user_id=user.id,
            status="completed",
            completed_at=now,
        )
        db.add(run)
        db.flush()
        plan = LearningPlan(
            user_id=user.id,
            assessment_run_id=run.id,
            recommendation_text="test",
            version=1,
            generated_at=now,
        )
        db.add(plan)
        db.flush()
        db.add_all(
            [
                LearningPlanItem(
                    plan_id=plan.id,
                    lesson_id="variables-v1",
                    skill_id="python.variables",
                    position=1,
                    focus_score=0.5,
                    rationale="test",
                ),
                LearningPlanItem(
                    plan_id=plan.id,
                    lesson_id="conditions-v1",
                    skill_id="python.conditionals",
                    position=2,
                    focus_score=0.5,
                    rationale="test",
                ),
                LessonCompletion(
                    user_id=user.id,
                    lesson_id="variables-v1",
                    answer="6",
                    completed_at=now,
                ),
                UserSkill(
                    user_id=user.id,
                    skill_id="python.variables",
                    evidence_count=1,
                    next_review_at=now - timedelta(days=2),
                ),
                UserSkill(
                    user_id=user.id,
                    skill_id="python.conditionals",
                    evidence_count=1,
                    next_review_at=now - timedelta(days=2),
                ),
            ]
        )
        db.commit()

    response = client.get("/learning/plan")
    assert response.status_code == 200
    items = response.json()["items"]
    reviews = [item for item in items if item["kind"] == "review"]
    assert [item["skill_id"] for item in reviews] == ["python.variables"]
    assert reviews[0]["position"] > max(
        item["position"] for item in items if item["kind"] == "lesson"
    )
    assert reviews[0]["overdue_days"] >= 1
