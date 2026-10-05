"""Trusted authored Python practice. Grading keys never enter public responses.

The worker receives this catalog at build time, not learner-supplied tests.
Each public exercise has a distinct immutable ID from the lesson quiz.
"""
from __future__ import annotations

RUNNER_EXERCISES: dict[str, dict] = {}


def trusted_exercise(skill_id: str, exercise_id: str) -> bool:
    row = RUNNER_EXERCISES.get(exercise_id)
    return row is not None and row["skill_id"] == skill_id


def trusted_exercises_for_skill(skill_id: str) -> list[str]:
    return sorted(key for key, row in RUNNER_EXERCISES.items() if row["skill_id"] == skill_id)


def public_exercise(exercise_id: str) -> dict:
    row = RUNNER_EXERCISES[exercise_id]
    return {
        "exercise_id": row["exercise_id"], "version": row["version"],
        "lesson_id": row["lesson_id"], "skill_id": row["skill_id"],
        "prompt": row["prompt"], "starter_code": row["starter_code"],
        "input_description": row["input_description"],
        "public_examples": row["public_examples"],
        "public_example_inputs": [case["args"][0] for case in row["cases"] if case["visibility"] == "public"],
    }


def authored_exercise(lesson_id: str, skill_id: str, prompt: str, solution: str,
                      public: list[tuple], hidden: list[tuple]) -> dict:
    exercise_id = lesson_id + "-code"
    return {
        "exercise_id": exercise_id, "version": 1, "lesson_id": lesson_id,
        "skill_id": skill_id, "prompt": prompt,
        "input_description": "Один JSON-объект payload с полями, перечисленными в условии; результат должен быть JSON-совместимым.",
        "starter_code": "def solve(payload):\n    # Верните результат в формате, описанном в условии.\n    raise NotImplementedError\n",
        "solution": solution,
        "public_examples": [{"input": payload, "output": expected} for payload, expected in public],
        "tests": [
            {"input": payload, "expected": expected, "visibility": visibility}
            for visibility, items in (("public", public), ("hidden", hidden))
            for payload, expected in items
        ],
        "cases": [
            {"args": [payload], "kwargs": {}, "expected": expected, "visibility": visibility}
            for visibility, items in (("public", public), ("hidden", hidden))
            for payload, expected in items
        ],
    }

from app.completion_content import TOPICS
from app.core_practice_content import CORE_PRACTICE
for _row in TOPICS:
    _item = authored_exercise(_row['lesson_id'], _row['skill'], _row['practice'], _row['solution'], _row['public'], _row['hidden'])
    RUNNER_EXERCISES[_item['exercise_id']] = _item
for _lesson, _skill, _prompt, _solution, _public, _hidden in CORE_PRACTICE:
    _item = authored_exercise(_lesson, _skill, _prompt, _solution, _public, _hidden)
    RUNNER_EXERCISES[_item['exercise_id']] = _item
for _item in RUNNER_EXERCISES.values():
    _item['hints'] = (
        (1,'direction','Разделите условие на входные данные, результат и граничные случаи.'),
        (2,'concept','Сопоставьте правило темы урока с требуемым поведением функции; вход и выход должны быть JSON-совместимыми.'),
        (3,'step','Проследите публичный пример вручную, затем проверьте случай из условия, в котором обычная ветка меняется.'),
        (4,'pseudocode','прочитать поля payload\nвычислить результат по контракту\nобработать границы из условия\nвернуть результат'),
        (5,'solution',_item['solution']),
    )
