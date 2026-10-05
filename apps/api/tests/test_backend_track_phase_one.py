"""Behaviour tests for the authored `python.backend` phase 1 track.

These tests assert what a learner can observe: which lessons exist, which
skill each covers, when a lesson unlocks, and how phase progress is reported.
They deliberately avoid asserting on the text of lesson prose.
"""

from collections import defaultdict
import subprocess
import sys

from sqlalchemy import select

from app.assessment_content import MAX_QUESTIONS
from app.backend_content import BACKEND_PHASES, BACKEND_PHASE_ONE_LESSONS
from app.db.models import ExerciseHint, ExerciseVersion, User, UserSkill
from app.db.session import get_db
from app.knowledge_check_content import CHECKS
from app.learning_content import EXERCISE_HINT_LADDERS, LESSONS
from app.main import app
from app.skill_graph import SKILLS
from test_auth import client, csrf


PHASE_ONE_SKILLS = (
    "backend.http_basics",
    "backend.rest",
    "backend.api_design",
    "backend.json",
    "backend.fastapi_basics",
    "backend.fastapi_routing",
    "backend.fastapi_dependencies",
    "backend.request_validation",
    "backend.response_models",
)
PHASE_ONE_LESSON_IDS = tuple(lesson["id"] for lesson in BACKEND_PHASE_ONE_LESSONS)
CORE_SKILL_IDS = frozenset(
    skill["id"] for skill in SKILLS if skill["category"] == "python.core"
)


def setup_user(test_client, email: str) -> None:
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


def finish_assessment(test_client) -> None:
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


def set_mastery(test_client, skill_ids: set[str], value: float) -> None:
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        for skill_id in skill_ids:
            row = db.scalar(
                select(UserSkill).where(
                    UserSkill.user_id == user.id,
                    UserSkill.skill_id == skill_id,
                )
            )
            if row is None:
                row = UserSkill(user_id=user.id, skill_id=skill_id)
                db.add(row)
            row.evidence_count = 1 if value >= 0.75 else 0
            row.independent_score = value
            row.knowledge_score = value
            row.practice_score = value
        db.commit()


def test_phase_one_covers_exactly_the_nine_published_backend_skills(client):
    graph_skills = {skill["id"] for skill in SKILLS}
    phase = next(item for item in BACKEND_PHASES if item["id"] == 1)

    assert phase["skill_ids"] == PHASE_ONE_SKILLS
    assert len(PHASE_ONE_LESSON_IDS) == len(set(PHASE_ONE_LESSON_IDS))
    assert {lesson["skill_id"] for lesson in BACKEND_PHASE_ONE_LESSONS} == set(
        PHASE_ONE_SKILLS
    )

    lessons = {lesson["id"]: lesson for lesson in LESSONS}
    for lesson in BACKEND_PHASE_ONE_LESSONS:
        assert lesson["id"] in lessons
        assert lesson["skill_id"] in graph_skills
        assert lesson["phase"] == 1
        assert lesson["answer"] in lesson["choices"]
        assert lesson["id"] in CHECKS
        assert lesson["id"] in EXERCISE_HINT_LADDERS


def test_every_backend_skill_belongs_to_exactly_one_authored_phase():
    backend_skills = {
        skill["id"] for skill in SKILLS if skill["category"] == "python.backend"
    }
    assignment = [
        skill_id
        for phase in BACKEND_PHASES
        for skill_id in phase["skill_ids"]
    ]

    assert sorted(assignment) == sorted(backend_skills)
    assert len(assignment) == len(set(assignment))


def test_phase_one_lessons_follow_the_authored_prerequisite_chain(client):
    setup_user(client, "backend-phase-one-graph@example.com")

    response = client.get("/skills/graph")
    assert response.status_code == 200
    graph = response.json()
    prerequisite_edges = {
        (edge["from"], edge["to"])
        for edge in graph["edges"]
        if edge["relation"] == "prerequisite"
    }
    graph_skill_ids = {skill["id"] for skill in SKILLS}
    lessons = {lesson["id"]: lesson for lesson in LESSONS}

    for lesson in BACKEND_PHASE_ONE_LESSONS:
        declared = set(lessons[lesson["id"]]["prerequisites"])
        assert declared
        for prerequisite in declared:
            assert prerequisite in graph_skill_ids
            assert (prerequisite, lesson["skill_id"]) in prerequisite_edges

    adjacency = defaultdict(set)
    for source, target in prerequisite_edges:
        adjacency[target].add(source)
    for lesson in BACKEND_PHASE_ONE_LESSONS:
        required = set()
        pending = [lesson["skill_id"]]
        while pending:
            current = pending.pop()
            for prerequisite in adjacency[current]:
                if prerequisite not in required:
                    required.add(prerequisite)
                    pending.append(prerequisite)
        required.discard(lesson["skill_id"])
        assert required, "each phase 1 skill has a reachable prerequisite chain"


def test_phase_one_is_locked_until_core_prerequisites_are_met(client):
    setup_user(client, "backend-phase-one-gate@example.com")
    finish_assessment(client)

    path = client.get("/learning/path")
    assert path.status_code == 200
    lessons = {item["id"]: item for item in path.json()["lessons"]}

    for lesson_id in PHASE_ONE_LESSON_IDS:
        assert lessons[lesson_id]["status"] == "locked"
        assert client.get(f"/learning/lessons/{lesson_id}").status_code == 409

    phases = {item["id"]: item for item in path.json()["phases"]}
    assert phases[1]["status"] == "locked"
    assert phases[1]["completed"] == 0


def test_phase_one_opens_only_after_its_core_prerequisite(client):
    setup_user(client, "backend-phase-one-unlock@example.com")
    finish_assessment(client)
    # The whole core chain gates the first backend lesson, because
    # `backend.http_basics` requires `python.functions`, whose own closure is
    # the entire core track.
    set_mastery(client, set(CORE_SKILL_IDS) - {"python.functions"}, 1.0)

    lessons = {
        item["id"]: item
        for item in client.get("/learning/path").json()["lessons"]
    }

    assert lessons["http-basics-v1"]["status"] == "locked"
    assert client.get("/learning/lessons/http-basics-v1").status_code == 409

    set_mastery(client, {"python.functions"}, 1.0)
    lessons = {
        item["id"]: item
        for item in client.get("/learning/path").json()["lessons"]
    }

    assert lessons["http-basics-v1"]["status"] == "available"
    assert lessons["rest-api-v1"]["status"] == "locked"
    assert client.get("/learning/lessons/http-basics-v1").status_code == 200
    assert client.get("/learning/lessons/rest-api-v1").status_code == 409


def test_phase_progress_is_reported_as_lesson_counts_without_percentages(client):
    setup_user(client, "backend-phase-progress@example.com")

    response = client.get("/learning/path")
    assert response.status_code == 200
    phases = response.json()["phases"]
    published = [item for item in phases if item["total"] > 0]

    assert [item["id"] for item in published] == [1]
    assert published[0]["completed"] == 0
    assert published[0]["total"] == len(PHASE_ONE_LESSON_IDS)
    assert published[0]["status"] in {"available", "locked"}
    assert "%" not in response.text


def test_each_phase_one_lesson_publishes_a_versioned_snapshot(client):
    setup_user(client, "backend-phase-snapshots@example.com")
    set_mastery(client, set(CORE_SKILL_IDS) | set(PHASE_ONE_SKILLS), 1.0)

    for lesson in BACKEND_PHASE_ONE_LESSONS:
        lesson_id = lesson["id"]
        response = client.get(f"/learning/lessons/{lesson_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == lesson_id
        assert body["skill_id"] == lesson["skill_id"]
        assert body["phase"] == 1
        assert "answer" not in body
        assert body["prerequisites"] == lesson["prerequisites"]

        checks = client.get(
            f"/learning/lessons/{lesson_id}/knowledge-check"
        )
        assert checks.status_code == 200
        assert checks.json() == [
            {
                "id": question["id"],
                "prompt": question["prompt"],
                "choices": question["choices"],
            }
            for question in CHECKS[lesson_id]
        ]

        ladder = EXERCISE_HINT_LADDERS[lesson_id]
        for level, kind, text in ladder["hints"]:
            hint = client.post(
                f"/learning/exercises/{lesson_id}/hints",
                headers={
                    "X-CSRF-Token": csrf(client),
                    "Idempotency-Key": f"backend-phase-{lesson_id}-{level}",
                },
                json={"level": level},
            )
            assert hint.status_code == 200
            assert hint.json() == {"level": level, "kind": kind, "text": text}

        with next(app.dependency_overrides[get_db]()) as db:
            version = db.scalar(
                select(ExerciseVersion).where(
                    ExerciseVersion.exercise_id == lesson_id,
                    ExerciseVersion.version == ladder["version"],
                )
            )
            assert version is not None
            snapshot = version.content_snapshot
            assert snapshot["lesson"]["skill_id"] == lesson["skill_id"]
            assert snapshot["checks"] == list(CHECKS[lesson_id])
            persisted = db.scalars(
                select(ExerciseHint)
                .where(ExerciseHint.exercise_version_id == version.id)
                .order_by(ExerciseHint.level)
            ).all()
            assert [
                (hint.level, hint.kind, hint.content) for hint in persisted
            ] == list(ladder["hints"])


def test_phase_one_practice_never_promises_runner_execution():
    forbidden = (
        "выполним твой код",
        "запустим твой код",
        "код будет выполнен",
        "проверим твой код",
    )
    for lesson in BACKEND_PHASE_ONE_LESSONS:
        text = " ".join(
            str(lesson[field])
            for field in ("goal", "theory", "body", "practice", "conclusion")
        ).casefold()
        for marker in forbidden:
            assert marker not in text, (lesson["id"], marker)


def test_phase_one_examples_print_exactly_the_published_output():
    """The documented output is checked against a real run, not written by eye."""
    for lesson in BACKEND_PHASE_ONE_LESSONS:
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", lesson["example"]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        assert completed.returncode == 0, (lesson["id"], completed.stderr[-500:])
        assert completed.stdout.replace("\r\n", "\n").strip() == lesson[
            "example_output"
        ].strip(), lesson["id"]
