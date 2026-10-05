from content_helpers import public_question_identity
from content_helpers import authored_answer, authored_wrong_answer
from collections import defaultdict
from copy import deepcopy

from sqlalchemy import select

from app.assessment_content import MAX_QUESTIONS
from app.db.models import ExerciseHint, ExerciseVersion, User, UserSkill
from app.db.session import get_db
from app.exercise_hints import _seed_exercise
from app.knowledge_check_content import CHECKS
from app.learning_content import EXERCISE_HINT_LADDERS, LESSONS
from app.main import app
from app.skill_graph import SKILLS
from test_auth import client, csrf


WAVE_C = (
    ("mutability-v1", "python.mutability", "python.scope"),
    ("strings-v1", "python.strings", "python.mutability"),
    ("numbers-v1", "python.numbers", "python.strings"),
    ("booleans-v1", "python.booleans", "python.numbers"),
)
WAVE_C_IDS = tuple(item[0] for item in WAVE_C)
SKILL_CHAIN = (
    "python.variables",
    "python.data_types",
    "python.conditionals",
    "python.loops",
    "python.functions",
    "python.parameters",
    "python.return_values",
    "python.scope",
    "python.mutability",
    "python.strings",
    "python.numbers",
    "python.booleans",
)
HINT_KINDS = ("direction", "concept", "step", "pseudocode", "solution")
EXPECTED_CHECK_IDS = {
    "mutability-v1": (
        "mutability-alias-v1",
        "mutability-rebind-v1",
        "mutability-object-v1",
    ),
    "strings-v1": (
        "strings-concat-v1",
        "strings-immutable-v1",
        "strings-format-v1",
    ),
    "numbers-v1": (
        "numbers-remainder-v1",
        "numbers-floor-v1",
        "numbers-division-v1",
    ),
    "booleans-v1": (
        "booleans-type-v1",
        "booleans-equality-v1",
        "booleans-result-v1",
    ),
}


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


def test_wave_c_lessons_match_exact_graph_edges_and_transitive_closure(client):
    setup_user(client, "wave-c-graph@example.com")

    response = client.get("/skills/graph")
    assert response.status_code == 200
    graph = response.json()
    skill_ids = {skill["id"] for skill in graph["skills"]}
    assert set(SKILL_CHAIN).issubset(skill_ids)

    prerequisites = defaultdict(set)
    for edge in graph["edges"]:
        assert edge["from"] in skill_ids
        assert edge["to"] in skill_ids
        if edge["relation"] == "prerequisite":
            prerequisites[edge["to"]].add(edge["from"])

    lessons = {lesson["id"]: lesson for lesson in LESSONS}
    for lesson_id, skill_id, direct_prerequisite in WAVE_C:
        assert lesson_id in lessons
        assert lessons[lesson_id]["skill_id"] == skill_id
        assert lessons[lesson_id]["prerequisites"] == [direct_prerequisite]
        assert (direct_prerequisite, skill_id) in {
            (edge["from"], edge["to"])
            for edge in graph["edges"]
            if edge["relation"] == "prerequisite"
        }

        required = set()
        pending = list(prerequisites[skill_id])
        while pending:
            prerequisite = pending.pop()
            if prerequisite in required:
                continue
            required.add(prerequisite)
            pending.extend(prerequisites[prerequisite])

        skill_index = SKILL_CHAIN.index(skill_id)
        assert required == set(SKILL_CHAIN[:skill_index])


def test_wave_c_checks_choice_feedback_hints_and_schema_two_snapshots(client):
    setup_user(client, "wave-c-snapshots@example.com")
    set_mastery(client, set(SKILL_CHAIN), 1.0)

    lessons = {lesson["id"]: lesson for lesson in LESSONS}
    assert set(WAVE_C_IDS).issubset(lessons)

    for lesson_id in WAVE_C_IDS:
        questions = CHECKS[lesson_id]
        assert tuple(question["id"] for question in questions) == EXPECTED_CHECK_IDS[lesson_id]
        for question in questions:
            assert set(question["choice_explanations"]) == set(question["choices"])
            assert all(
                isinstance(explanation, str) and explanation.strip()
                for explanation in question["choice_explanations"].values()
            )

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

        ladder = EXERCISE_HINT_LADDERS[lesson_id]
        assert ladder["lesson_id"] == lesson_id
        assert ladder["version"] == 1
        assert [level for level, _, _ in ladder["hints"]] == [1, 2, 3, 4, 5]
        assert [kind for _, kind, _ in ladder["hints"]] == list(HINT_KINDS)
        solution_text = ladder["hints"][4][2]

        for level, kind, text in ladder["hints"]:
            hint_response = client.post(
                f"/learning/exercises/{lesson_id}/hints",
                headers={
                    "X-CSRF-Token": csrf(client),
                    "Idempotency-Key": f"wave-c-{lesson_id}-{level}",
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
                assert text != solution_text
                assert solution_text not in text

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
            assert snapshot["lesson"] == lessons[lesson_id]
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
            ] == list(ladder["hints"])


def test_wave_c_snapshot_version_is_immutable_when_authored_content_changes(
    client, monkeypatch
):
    setup_user(client, "wave-c-versioning@example.com")
    from app import exercise_snapshots

    lesson_id = "mutability-v1"
    original_lesson = next(lesson for lesson in LESSONS if lesson["id"] == lesson_id)
    original_check = CHECKS[lesson_id][0]
    original_ladder = EXERCISE_HINT_LADDERS[lesson_id]

    with next(app.dependency_overrides[get_db]()) as db:
        first = _seed_exercise(db, lesson_id)
        db.commit()
        first_id = first.id
        first_snapshot = deepcopy(first.content_snapshot)

    changed_lesson = {**original_lesson, "body": "Version two body."}
    changed_check = {
        **original_check,
        "prompt": "Version two prompt.",
        "choice_explanations": {
            choice: f"Version two: {choice}"
            for choice in original_check["choices"]
        },
    }
    changed_ladder = {
        **original_ladder,
        "version": 2,
        "hints": tuple(
            (level, kind, f"Version two: {text}")
            for level, kind, text in original_ladder["hints"]
        ),
    }
    authored_lessons = tuple(
        changed_lesson if lesson["id"] == lesson_id else lesson
        for lesson in exercise_snapshots.LESSONS
    )
    monkeypatch.setattr(exercise_snapshots, "LESSONS", authored_lessons)
    monkeypatch.setattr(
        exercise_snapshots,
        "CHECKS",
        {**exercise_snapshots.CHECKS, lesson_id: (changed_check,)},
    )
    monkeypatch.setattr(
        exercise_snapshots,
        "EXERCISE_HINT_LADDERS",
        {**exercise_snapshots.EXERCISE_HINT_LADDERS, lesson_id: changed_ladder},
    )

    with next(app.dependency_overrides[get_db]()) as db:
        second = _seed_exercise(db, lesson_id)
        db.commit()
        assert second.version == 2
        assert second.content_snapshot["lesson"]["body"] == changed_lesson["body"]
        assert second.content_snapshot["checks"] == [changed_check]
        assert db.get(ExerciseVersion, first_id).content_snapshot == first_snapshot
        versions = db.scalars(
            select(ExerciseVersion).where(
                ExerciseVersion.exercise_id == lesson_id
            )
        ).all()
        assert {version.version for version in versions} == {1, 2}


def test_wave_c_path_and_plan_require_prerequisites_and_never_recommend_locked(
    client,
):
    setup_user(client, "wave-c-readiness@example.com")
    finish_assessment(client)
    set_mastery(client, set(SKILL_CHAIN), 0.0)

    path = client.get("/learning/path")
    assert path.status_code == 200
    path_by_id = {lesson["id"]: lesson for lesson in path.json()["lessons"]}
    plan = client.get("/learning/plan")
    assert plan.status_code == 200
    plan_by_id = {item["lesson_id"]: item for item in plan.json()["items"]}

    locked_ids = {
        lesson["id"]
        for lesson in path.json()["lessons"]
        if lesson["status"] == "locked"
    }
    assert set(WAVE_C_IDS).issubset(locked_ids)
    assert path.json()["next_lesson_id"] not in locked_ids
    assert plan.json()["recommended_lesson_id"] not in locked_ids
    assert all(
        item["status"] != "recommended"
        or item["lesson_id"] not in locked_ids
        for item in plan.json()["items"]
    )
    for lesson_id in WAVE_C_IDS:
        assert path_by_id[lesson_id]["status"] == "locked"
        assert plan_by_id[lesson_id]["status"] == "locked"
        assert client.get(f"/learning/lessons/{lesson_id}").status_code == 409

    for index, (lesson_id, skill_id, _) in enumerate(WAVE_C):
        prerequisite_closure = set(SKILL_CHAIN[: SKILL_CHAIN.index(skill_id)])
        set_mastery(client, prerequisite_closure, 1.0)

        path = client.get("/learning/path")
        assert path.status_code == 200
        path_by_id = {lesson["id"]: lesson for lesson in path.json()["lessons"]}
        plan = client.get("/learning/plan")
        assert plan.status_code == 200
        plan_by_id = {item["lesson_id"]: item for item in plan.json()["items"]}
        assert path_by_id[lesson_id]["status"] == "available"
        assert plan_by_id[lesson_id]["status"] in {"recommended", "up_next"}
        assert client.get(f"/learning/lessons/{lesson_id}").status_code == 200
        for later_id in WAVE_C_IDS[index + 1 :]:
            assert path_by_id[later_id]["status"] == "locked"
            assert plan_by_id[later_id]["status"] == "locked"

        set_mastery(client, {skill_id}, 1.0)
