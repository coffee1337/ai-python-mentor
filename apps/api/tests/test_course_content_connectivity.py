from collections import defaultdict

from sqlalchemy import select

from app.assessment_content import MAX_QUESTIONS
from app.db.models import (
    ExerciseHint,
    ExerciseVersion,
    LessonCompletion,
    User,
    UserSkill,
)
from app.db.session import get_db
from app.knowledge_check_content import CHECKS
from app.learning_content import EXERCISE_HINT_LADDERS, LESSONS
from app.main import app
from app.skill_graph import SKILLS
from test_auth import client, csrf


def setup_user(test_client, email="course-connectivity@example.com"):
    assert test_client.post(
        "/auth/register",
        json={"email": email, "password": "safe-password"},
    ).status_code == 201
    assert test_client.post(
        "/onboarding",
        headers={"X-CSRF-Token": csrf(test_client)},
        json={
            "experience_level": "beginner",
            "target_role": "Python Backend",
            "weekly_minutes": 180,
        },
    ).status_code == 200


def grant_full_graph_mastery():
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        db.add_all(
            UserSkill(
                user_id=user.id,
                skill_id=skill["id"],
                evidence_count=1,
                independent_score=1.0,
                knowledge_score=1.0,
                practice_score=1.0,
            )
            for skill in SKILLS
        )
        db.commit()


def finish_assessment(test_client):
    state = test_client.get("/assessment").json()
    for _ in range(MAX_QUESTIONS):
        question = state["question"]
        response = test_client.post(
            "/assessment/answers",
            headers={"X-CSRF-Token": csrf(test_client)},
            json={
                "question_id": question["id"],
                "answer": question["choices"][0],
            },
        )
        assert response.status_code == 200
        state = response.json()["state"]
    assert state["completed"] is True


def test_active_lessons_resolve_to_an_acyclic_graph_with_closed_prerequisites(client):
    setup_user(client, "course-graph@example.com")

    response = client.get("/skills/graph")
    assert response.status_code == 200
    graph = response.json()
    skill_ids = {skill["id"] for skill in graph["skills"]}
    active_lessons = {lesson["id"]: lesson for lesson in LESSONS}

    assert set(active_lessons) == {
        lesson_id
        for skill in graph["skills"]
        for lesson_id in skill["lesson_ids"]
        if lesson_id in active_lessons
    }
    for lesson in active_lessons.values():
        matching_skills = [
            skill["id"]
            for skill in graph["skills"]
            if lesson["id"] in skill["lesson_ids"]
        ]
        assert matching_skills == [lesson["skill_id"]]

    adjacency = defaultdict(list)
    for edge in graph["edges"]:
        assert edge["from"] in skill_ids
        assert edge["to"] in skill_ids
        if edge["relation"] == "prerequisite":
            adjacency[edge["to"]].append(edge["from"])

    visited = set()
    visiting = set()

    def visit(skill_id):
        if skill_id in visiting:
            raise AssertionError(f"prerequisite cycle at {skill_id}")
        if skill_id in visited:
            return
        visiting.add(skill_id)
        for prerequisite in adjacency[skill_id]:
            assert prerequisite in skill_ids
            visit(prerequisite)
        visiting.remove(skill_id)
        visited.add(skill_id)

    for skill_id in skill_ids:
        visit(skill_id)


def test_each_active_lesson_has_exact_check_hint_ladder_and_published_version(client):
    setup_user(client, "course-snapshots@example.com")
    grant_full_graph_mastery()

    active_lessons = {lesson["id"]: lesson for lesson in LESSONS}
    assert set(CHECKS) == set(active_lessons)
    assert set(EXERCISE_HINT_LADDERS) == set(active_lessons)

    for lesson_id, lesson in active_lessons.items():
        check_response = client.get(
            f"/learning/lessons/{lesson_id}/knowledge-check"
        )
        assert check_response.status_code == 200
        assert check_response.json() == [
            {
                "id": question["id"],
                "prompt": question["prompt"],
                "choices": question["choices"],
            }
            for question in CHECKS[lesson_id]
        ]

        ladder = EXERCISE_HINT_LADDERS[lesson_id]
        for level, kind, text in ladder["hints"]:
            hint_response = client.post(
                f"/learning/exercises/{lesson_id}/hints",
                headers={
                    "X-CSRF-Token": csrf(client),
                    "Idempotency-Key": f"connectivity-{lesson_id}-{level}",
                },
                json={"level": level},
            )
            assert hint_response.status_code == 200
            assert hint_response.json() == {
                "level": level,
                "kind": kind,
                "text": text,
            }

        with next(app.dependency_overrides[get_db]()) as db:
            version = db.scalar(
                select(ExerciseVersion).where(
                    ExerciseVersion.exercise_id == lesson_id,
                    ExerciseVersion.version == ladder["version"],
                )
            )
            assert version is not None
            assert version.lesson_id == lesson_id
            snapshot = version.content_snapshot
            assert snapshot["exercise_id"] == lesson_id
            assert snapshot["version"] == ladder["version"]
            assert snapshot["lesson"] == lesson
            assert snapshot["checks"] == list(CHECKS[lesson_id])
            assert snapshot["hints"] == [
                {"level": level, "kind": kind, "text": text}
                for level, kind, text in ladder["hints"]
            ]

            persisted_hints = db.scalars(
                select(ExerciseHint)
                .where(ExerciseHint.exercise_version_id == version.id)
                .order_by(ExerciseHint.level)
            ).all()
            assert [
                (hint.level, hint.kind, hint.content)
                for hint in persisted_hints
            ] == list(ladder["hints"])

            assert (
                db.scalar(
                    select(ExerciseVersion).where(
                        ExerciseVersion.exercise_id == lesson_id,
                        ExerciseVersion.version == ladder["version"],
                    )
                ).id
                == version.id
            )


def test_path_plan_and_curriculum_never_recommend_a_locked_lesson(client):
    setup_user(client, "course-availability@example.com")
    finish_assessment(client)

    path = client.get("/learning/path")
    assert path.status_code == 200
    path_body = path.json()
    locked_ids = {
        lesson["id"]
        for lesson in path_body["lessons"]
        if lesson["status"] == "locked"
    }
    assert locked_ids
    assert path_body["next_lesson_id"] not in locked_ids

    plan = client.get("/learning/plan")
    assert plan.status_code == 200
    plan_body = plan.json()
    assert plan_body["recommended_lesson_id"] not in locked_ids
    assert all(
        item["lesson_id"] not in locked_ids
        for item in plan_body["items"]
        if item["status"] == "recommended"
    )

    curriculum = client.get("/learning/curriculum")
    assert curriculum.status_code == 200
    for session in curriculum.json()["sessions"]:
        for activity in session["activities"]:
            assert activity["lesson_id"] not in locked_ids
            assert activity["availability"] != "locked"


def test_legacy_variables_completion_does_not_open_conditions_without_data_types(
    client,
):
    setup_user(client, "course-legacy-mapping@example.com")

    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        db.add(
            LessonCompletion(
                user_id=user.id,
                lesson_id="variables-v1",
                answer="6",
            )
        )
        db.commit()

    path = client.get("/learning/path")
    assert path.status_code == 200
    lessons = {lesson["id"]: lesson for lesson in path.json()["lessons"]}
    assert lessons["variables-v1"]["status"] == "completed"
    assert lessons["conditions-v1"]["status"] == "locked"
    assert path.json()["next_lesson_id"] != "conditions-v1"
    assert client.get("/learning/lessons/conditions-v1").status_code == 409
