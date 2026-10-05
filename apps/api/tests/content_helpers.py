"""Test helpers for publishing newly-versioned schema-v2 authored checks."""


def authored_answer(question_id: str) -> str:
    from app.assessment_content import QUESTIONS
    from app.knowledge_check_content import CHECKS
    questions = [*QUESTIONS, *(question for checks in CHECKS.values() for question in checks)]
    return next(question["answer"] for question in questions if question["id"] == question_id)


def authored_wrong_answer(question_id: str) -> str:
    from app.knowledge_check_content import CHECKS
    question = next(question for checks in CHECKS.values() for question in checks if question["id"] == question_id)
    return next(choice for choice in question["choices"] if choice != question["answer"])


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


def public_question_identity(questions):
    return [{**question, "choices": sorted(question["choices"])} for question in questions]
