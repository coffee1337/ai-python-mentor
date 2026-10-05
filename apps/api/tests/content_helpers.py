"""Test helpers for publishing newly-versioned schema-v2 authored checks."""


def enable_choice_feedback(monkeypatch, exercise_id: str, *, prefix: str = "test") -> None:
    from app import exercise_snapshots

    checks = exercise_snapshots.CHECKS
    questions = tuple(
        {
            **question,
            "choice_explanations": {
                choice: f"{prefix}:{question['id']}:{choice}"
                for choice in question["choices"]
            },
        }
        for question in checks[exercise_id]
    )
    monkeypatch.setattr(
        exercise_snapshots,
        "CHECKS",
        {**checks, exercise_id: questions},
    )
