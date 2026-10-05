from copy import deepcopy

from sqlalchemy import select

from app.db.models import ExerciseVersion
from app.db.session import get_db
from app.exercise_hints import _seed_exercise
from app.main import app
from test_auth import client


def test_new_lesson_checks_and_hints_publish_as_immutable_schema_two_snapshot(
    client, monkeypatch
):
    from app import exercise_snapshots

    lesson = {
        "id": "snapshot-contract-v1",
        "title": "Snapshot contract",
        "skill_id": "python.functions",
        "minutes": 12,
        "body": "Lesson body",
        "example": "print('ok')",
        "question": "Which answer?",
        "choices": ["yes", "no"],
        "answer": "yes",
        "goal": "Capture all authored fields",
        "practice": "Explain the result without running learner code.",
    }
    check = {
        "id": "snapshot-contract-check-v1",
        "prompt": "What is selected?",
        "choices": ["yes", "no"],
        "answer": "yes",
        "explanation": "General explanation.",
        "choice_explanations": {
            "yes": "The selected value is yes.",
            "no": "The selected value is no.",
        },
    }
    ladder = {
        "version": 1,
        "lesson_id": lesson["id"],
        "hints": (
            (1, "direction", "Review the prompt."),
            (2, "concept", "Recall the concept."),
            (3, "step", "Apply one step."),
            (4, "pseudocode", "Outline the reasoning."),
            (5, "solution", "The authored solution."),
        ),
    }
    monkeypatch.setattr(exercise_snapshots, "LESSONS", (*exercise_snapshots.LESSONS, lesson))
    monkeypatch.setattr(
        exercise_snapshots,
        "CHECKS",
        {**exercise_snapshots.CHECKS, lesson["id"]: (check,)},
    )
    monkeypatch.setattr(
        exercise_snapshots,
        "EXERCISE_HINT_LADDERS",
        {**exercise_snapshots.EXERCISE_HINT_LADDERS, lesson["id"]: ladder},
    )

    with next(app.dependency_overrides[get_db]()) as db:
        first = _seed_exercise(db, lesson["id"])
        db.commit()
        first_id = first.id
        first_snapshot = deepcopy(first.content_snapshot)
        assert first_snapshot["schema_version"] == 2
        assert first_snapshot["lesson"]["goal"] == lesson["goal"]
        assert first_snapshot["checks"] == [check]
        assert first_snapshot["hints"][0]["text"] == ladder["hints"][0][2]

    changed_lesson = {**lesson, "body": "Changed only for the next authored version."}
    changed_check = {
        **check,
        "choice_explanations": {
            "yes": "Version two selected yes.",
            "no": "Version two selected no.",
        },
    }
    changed_ladder = {
        **ladder,
        "version": 2,
        "hints": tuple(
            (level, kind, "Version two: " + text)
            for level, kind, text in ladder["hints"]
        ),
    }
    monkeypatch.setattr(
        exercise_snapshots,
        "LESSONS",
        (*exercise_snapshots.LESSONS[:-1], changed_lesson),
    )
    monkeypatch.setattr(
        exercise_snapshots,
        "CHECKS",
        {**exercise_snapshots.CHECKS, lesson["id"]: (changed_check,)},
    )
    monkeypatch.setattr(
        exercise_snapshots,
        "EXERCISE_HINT_LADDERS",
        {**exercise_snapshots.EXERCISE_HINT_LADDERS, lesson["id"]: changed_ladder},
    )

    with next(app.dependency_overrides[get_db]()) as db:
        second = _seed_exercise(db, lesson["id"])
        db.commit()
        assert second.version == 2
        assert second.content_snapshot["lesson"]["body"] == changed_lesson["body"]
        persisted_first = db.get(ExerciseVersion, first_id)
        assert persisted_first.content_snapshot == first_snapshot
        versions = db.scalars(
            select(ExerciseVersion).where(
                ExerciseVersion.exercise_id == lesson["id"]
            )
        ).all()
        assert {version.version for version in versions} == {1, 2}
