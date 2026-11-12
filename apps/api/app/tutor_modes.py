"""Tutor modes: one tutor, eight behaviours, chosen by the learner or by signals.

Every mode is a bounded instruction block on top of the same trusted system prompt;
the mode never changes what may be revealed (authored answers stay private) and it
never grants the model new capabilities.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CodingAttempt, MentorMessage, User

MODES: dict[str, dict[str, str]] = {
    "teach": {
        "title": "Объяснение",
        "rules": (
            "Teach the concept behind the question in plain language: define the terms, "
            "walk one line at a time and use a small everyday analogy. End with one check "
            "question about the learner's understanding."
        ),
    },
    "socratic": {
        "title": "Сократовский диалог",
        "rules": (
            "Do not explain directly. Ask one focused question at a time that makes the "
            "learner's own reasoning visible, and react to their answer with the next "
            "question. Never state the graded answer."
        ),
    },
    "hint": {
        "title": "Подсказка",
        "rules": (
            "Give the smallest next step and nothing beyond it: name what to look at, not "
            "what the result is. One sentence of direction plus one question."
        ),
    },
    "debug_coach": {
        "title": "Разбор ошибки",
        "rules": (
            "Treat the learner's code as evidence. Name the class of the defect, ask which "
            "line produces the observed behaviour, and suggest one experiment to confirm "
            "the hypothesis. Do not rewrite the solution."
        ),
    },
    "review": {
        "title": "Ревью кода",
        "rules": (
            "Review the learner's code by asking questions about correctness, edge cases, "
            "readability and tests, in that order. Name a concern as a question, never as a "
            "patch, and let the learner decide the change."
        ),
    },
    "examiner": {
        "title": "Проверка",
        "rules": (
            "Do not help. Ask one short verification question about the current topic and "
            "evaluate the answer the learner gives. Authoring answers stay private: never "
            "confirm a graded answer, only say whether the reasoning is on track."
        ),
    },
    "interviewer": {
        "title": "Собеседование",
        "rules": (
            "Act as a technical interviewer for a junior Python backend role. Ask one "
            "question, wait for the answer, follow up on the weakest part, and finish with "
            "one sentence of feedback on the reasoning, not on the verdict."
        ),
    },
    "project_mentor": {
        "title": "Проект",
        "rules": (
            "Focus on the learner's project: scope, milestones, what to build next and how "
            "to verify it. Keep the advice concrete and small enough for one session."
        ),
    },
}

DEFAULT_MODE = "teach"


class UnknownMode(ValueError):
    pass


def normalize(mode: str | None) -> str:
    value = (mode or DEFAULT_MODE).strip().casefold().replace("-", "_")
    if value not in MODES:
        raise UnknownMode(value)
    return value


def system_prompt(base: str, mode: str) -> str:
    """Append the mode block to the trusted base prompt."""
    rules = MODES[mode]["rules"]
    return f"{base}\nMode: {mode} ({MODES[mode]['title']}). {rules}"


def signals(db: Session, user: User, lesson_id: str) -> dict:
    """Objective signals that justify switching the mode without asking."""
    failed = db.scalar(
        select(func.count()).select_from(CodingAttempt).where(
            CodingAttempt.user_id == user.id,
            CodingAttempt.exercise_id == lesson_id,
            CodingAttempt.status == "failed",
        )
    ) or 0
    recent = list(db.scalars(
        select(MentorMessage).where(
            MentorMessage.conversation_id.in_(
                select(MentorMessage.conversation_id).where(MentorMessage.role == "user").limit(1)
            ),
            MentorMessage.role == "user",
        ).order_by(MentorMessage.created_at.desc()).limit(6)
    ))
    confusion = sum(
        1 for message in recent
        if any(phrase in message.content.casefold() for phrase in ("не понимаю", "непонятно", "с чего начать", "запутался"))
    )
    return {"failed_runs": int(failed), "confusion_signals": confusion}


def suggest(db: Session, user: User, lesson_id: str, requested: str | None = None) -> tuple[str, str]:
    """Return (mode, reason). An explicit choice always wins over the heuristic."""
    if requested:
        return normalize(requested), "explicit"
    state = signals(db, user, lesson_id)
    if state["confusion_signals"] >= 2:
        return "teach", "repeated_confusion"
    if state["failed_runs"] >= 3:
        return "debug_coach", "failed_runs"
    return DEFAULT_MODE, "default"


def catalogue() -> list[dict[str, str]]:
    return [{"id": key, "title": value["title"]} for key, value in MODES.items()]
