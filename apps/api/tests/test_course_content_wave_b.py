from content_helpers import public_question_identity
from content_helpers import authored_answer, authored_wrong_answer
from sqlalchemy import select

from app.assessment_content import MAX_QUESTIONS
from app.db.models import ExerciseHint, ExerciseVersion, User, UserSkill
from app.db.session import get_db
from app.knowledge_check_content import CHECKS
from app.learning_content import EXERCISE_HINT_LADDERS, LESSONS
from app.main import app
from app.runner import runner
from app.skill_graph import SKILLS
from test_auth import client, csrf


WAVE_B = (
    ("functions-v1", "python.functions", "python.loops"),
    ("parameters-v1", "python.parameters", "python.functions"),
    ("return-values-v1", "python.return_values", "python.parameters"),
    ("scope-v1", "python.scope", "python.return_values"),
)
WAVE_B_IDS = tuple(item[0] for item in WAVE_B)
WAVE_B_SKILLS = tuple(item[1] for item in WAVE_B)
BASE_PREREQUISITES = (
    "python.variables",
    "python.data_types",
    "python.conditionals",
    "python.loops",
)
HINT_KINDS = ("direction", "concept", "step", "pseudocode", "solution")


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
    state = test_client.get("/assessment")
    assert state.status_code == 200
    payload = state.json()
    for _ in range(MAX_QUESTIONS):
        question = payload["question"]
        response = test_client.post(
            "/assessment/answers",
            headers={"X-CSRF-Token": csrf(test_client)},
            json={
                "question_id": question["id"],
                "answer": authored_answer(question["id"]),
            },
        )
        assert response.status_code == 200
        payload = response.json()["state"]
    assert payload["completed"] is True


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


def grant_full_graph_mastery(test_client) -> None:
    set_mastery(test_client, {skill["id"] for skill in SKILLS}, 1.0)


def test_wave_b_lessons_follow_exact_graph_prerequisite_chain(client):
    setup_user(client, "wave-b-graph@example.com")

    lessons = {lesson["id"]: lesson for lesson in LESSONS}
    assert set(WAVE_B_IDS).issubset(lessons), (
        "Wave B authored lessons are not all published: "
        f"missing={sorted(set(WAVE_B_IDS) - set(lessons))}"
    )

    graph_response = client.get("/skills/graph")
    assert graph_response.status_code == 200
    graph = graph_response.json()
    skill_ids = {skill["id"] for skill in graph["skills"]}
    prerequisite_edges = {
        (edge["from"], edge["to"])
        for edge in graph["edges"]
        if edge["relation"] == "prerequisite"
    }

    expected_chain = list(BASE_PREREQUISITES) + list(WAVE_B_SKILLS)
    assert all(skill_id in skill_ids for skill_id in expected_chain)
    assert set(zip(expected_chain, expected_chain[1:])).issubset(prerequisite_edges)
    for lesson_id, skill_id, prerequisite in WAVE_B:
        lesson = lessons[lesson_id]
        assert lesson["skill_id"] == skill_id
        assert lesson["prerequisites"] == [prerequisite]
        assert (prerequisite, skill_id) in prerequisite_edges

    assert [item[1] for item in WAVE_B] == [
        "python.functions",
        "python.parameters",
        "python.return_values",
        "python.scope",
    ]
    assert [item[2] for item in WAVE_B] == [
        "python.loops",
        "python.functions",
        "python.parameters",
        "python.return_values",
    ]


def test_wave_b_checks_hints_and_snapshots_are_exact_and_non_leaking(client):
    setup_user(client, "wave-b-snapshot@example.com")
    grant_full_graph_mastery(client)

    lessons = {lesson["id"]: lesson for lesson in LESSONS}
    assert set(WAVE_B_IDS).issubset(lessons)
    assert all(lesson_id in CHECKS for lesson_id in WAVE_B_IDS)
    assert all(lesson_id in EXERCISE_HINT_LADDERS for lesson_id in WAVE_B_IDS)

    for lesson_id in WAVE_B_IDS:
        lesson = lessons[lesson_id]
        questions = CHECKS[lesson_id]
        ladder = EXERCISE_HINT_LADDERS[lesson_id]
        assert ladder["lesson_id"] == lesson_id
        assert ladder["version"] == 1
        assert [level for level, _, _ in ladder["hints"]] == [1, 2, 3, 4, 5]
        assert [kind for _, kind, _ in ladder["hints"]] == list(HINT_KINDS)

        check_response = client.get(
            f"/learning/lessons/{lesson_id}/knowledge-check"
        )
        assert check_response.status_code == 200
        assert public_question_identity(check_response.json()) == public_question_identity([
            {
                "id": question["id"],
                "prompt": question["prompt"],
                "choices": question["choices"],
            }
            for question in questions
        ])

        for level, kind, text in ladder["hints"]:
            hint_response = client.post(
                f"/learning/exercises/{lesson_id}/hints",
                headers={
                    "X-CSRF-Token": csrf(client),
                    "Idempotency-Key": f"wave-b-{lesson_id}-{level}",
                },
                json={"level": level},
            )
            assert hint_response.status_code == 200
            assert hint_response.json() == {
                "level": level,
                "kind": kind,
                "text": text,
            }
            if level < 5:
                assert kind in HINT_KINDS[:4]
                assert text.strip()
                assert text != ladder["hints"][4][2]
                assert ladder["hints"][4][2] not in text

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
            assert snapshot["schema_version"] == 2
            assert snapshot["exercise_id"] == lesson_id
            assert snapshot["version"] == ladder["version"]
            assert snapshot["lesson"] == lesson
            assert snapshot["checks"] == list(questions)
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
            ] == [tuple(hint) for hint in ladder["hints"]]


def test_wave_b_path_plan_and_lesson_access_wait_for_each_prerequisite(client):
    setup_user(client, "wave-b-access@example.com")
    finish_assessment(client)
    set_mastery(client, set(BASE_PREREQUISITES) | set(WAVE_B_SKILLS), 0.0)

    lessons = {lesson["id"]: lesson for lesson in LESSONS}
    assert set(WAVE_B_IDS).issubset(lessons)

    initial_path = client.get("/learning/path")
    assert initial_path.status_code == 200
    initial_by_id = {lesson["id"]: lesson for lesson in initial_path.json()["lessons"]}
    initial_plan = client.get("/learning/plan")
    assert initial_plan.status_code == 200
    initial_plan_by_id = {
        item["lesson_id"]: item for item in initial_plan.json()["items"]
    }
    for lesson_id in WAVE_B_IDS:
        assert initial_by_id[lesson_id]["status"] == "locked"
        assert initial_plan_by_id[lesson_id]["status"] == "locked"
        assert client.get(f"/learning/lessons/{lesson_id}").status_code == 409

    prerequisite_closure = {
        "functions-v1": set(BASE_PREREQUISITES),
        "parameters-v1": set(BASE_PREREQUISITES) | {"python.functions"},
        "return-values-v1": set(BASE_PREREQUISITES)
        | {"python.functions", "python.parameters"},
        "scope-v1": set(BASE_PREREQUISITES)
        | {"python.functions", "python.parameters", "python.return_values"},
    }
    for index, (lesson_id, skill_id, _) in enumerate(WAVE_B):
        set_mastery(client, prerequisite_closure[lesson_id], 1.0)

        path = client.get("/learning/path")
        assert path.status_code == 200
        path_by_id = {lesson["id"]: lesson for lesson in path.json()["lessons"]}
        assert path_by_id[lesson_id]["status"] == "available"

        plan = client.get("/learning/plan")
        assert plan.status_code == 200
        plan_by_id = {item["lesson_id"]: item for item in plan.json()["items"]}
        assert plan_by_id[lesson_id]["status"] in {"recommended", "up_next"}
        assert client.get(f"/learning/lessons/{lesson_id}").status_code == 200
        for later_id in WAVE_B_IDS[index + 1 :]:
            assert path_by_id[later_id]["status"] == "locked"
            assert plan_by_id[later_id]["status"] == "locked"

        set_mastery(client, {skill_id}, 1.0)


def test_wave_b_learning_surfaces_do_not_execute_runner(client, monkeypatch):
    setup_user(client, "wave-b-runner@example.com")
    grant_full_graph_mastery(client)
    calls = []

    def forbidden_runner(**kwargs):
        calls.append(kwargs)
        raise AssertionError("authored lesson flow must not execute Runner")

    monkeypatch.setattr(runner, "run", forbidden_runner)
    for lesson_id in WAVE_B_IDS:
        assert client.get(f"/learning/lessons/{lesson_id}").status_code == 200
        assert client.get(
            f"/learning/lessons/{lesson_id}/knowledge-check"
        ).status_code == 200
        assert client.get(
            f"/learning/exercises/{lesson_id}/attempts"
        ).status_code == 200
        assert client.post(
            f"/learning/exercises/{lesson_id}/hints",
            headers={
                "X-CSRF-Token": csrf(client),
                "Idempotency-Key": f"wave-b-runner-{lesson_id}",
            },
            json={"level": 1},
        ).status_code == 200

    assert calls == []
