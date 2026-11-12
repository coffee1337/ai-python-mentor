"""Content audit: the same checks the test suite enforces, available to operators.

The audit answers one question — is the published course complete enough to teach
from — and it is shareable with a reviewer instead of living only in a test file.
"""

from __future__ import annotations

import re

from app.exercise_snapshots import authored_snapshot
from app.knowledge_base import _planned_chunks
from app.learning_content import LESSONS
from app.runner_exercise_content import RUNNER_EXERCISES

PLACEHOLDERS = ("todo", "fixme", "tbd", "lorem", "placeholder", "заглушк", "xxx")
CYRILLIC = re.compile(r"[а-яё]")
LATIN = re.compile(r"[a-zA-Z]")


def russian_share(text: str) -> float:
    letters = len(CYRILLIC.findall(text.lower())) + len(LATIN.findall(text))
    return len(CYRILLIC.findall(text.lower())) / letters if letters else 0.0


def lesson_problems() -> list[str]:
    problems: list[str] = []
    for lesson in LESSONS:
        identifier = lesson["id"]
        for field in ("title", "body", "example", "question"):
            value = lesson.get(field) or ""
            if not str(value).strip():
                problems.append(f"{identifier}: пустое поле {field}")
            lowered = str(value).casefold()
            for marker in PLACEHOLDERS:
                if marker in lowered:
                    problems.append(f"{identifier}.{field}: заглушка «{marker}»")
        title, body = lesson.get("title") or "", lesson.get("body") or ""
        if russian_share(title) < 0.5:
            problems.append(f"{identifier}.title: нет русского текста")
        if russian_share(body) < 0.5:
            problems.append(f"{identifier}.body: нет русского текста")
        if len(body) < 200:
            problems.append(f"{identifier}.body: теория короче 200 символов")
        if lesson.get("practice_submission_type") != "guided_reading" and identifier + "-code" not in RUNNER_EXERCISES:
            problems.append(f"{identifier}: нет задания с исполнением кода")
    return problems


def exercise_problems() -> list[str]:
    problems: list[str] = []
    for exercise_id, row in RUNNER_EXERCISES.items():
        if not row.get("solution"):
            problems.append(f"{exercise_id}: нет эталонного решения")
        cases = row.get("tests") or []
        if len(cases) < 2:
            problems.append(f"{exercise_id}: меньше двух тестов")
        if not any(case.get("visibility") == "hidden" for case in cases):
            problems.append(f"{exercise_id}: нет скрытых тестов")
        solution = row.get("solution") or ""
        if "NotImplementedError" in solution:
            problems.append(f"{exercise_id}: решение содержит заглушку")
    return problems


def chunk_count() -> int:
    """Chunks the knowledge base would index for the authored course."""
    total = 0
    for lesson in LESSONS:
        try:
            snapshot = authored_snapshot(lesson["id"])
        except ValueError:
            continue
        total += len(_planned_chunks(snapshot, lesson["id"]))
    return total


def report() -> dict:
    lesson_issues = lesson_problems()
    exercise_issues = exercise_problems()
    return {
        "lessons": len(LESSONS),
        "exercises": len(RUNNER_EXERCISES),
        "cases": sum(len(row.get("tests") or []) for row in RUNNER_EXERCISES.values()),
        "knowledge_chunks": chunk_count(),
        "lesson_issues": lesson_issues,
        "exercise_issues": exercise_issues,
        "healthy": not lesson_issues and not exercise_issues,
    }
