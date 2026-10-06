"""Canonical, internal snapshots for authored exercise versions."""

from __future__ import annotations

import json
from typing import Any

from app.assessment_content import QUESTIONS, QUESTIONS_BY_ID
from app.knowledge_check_content import CHECKS
from app.learning_content import EXERCISE_HINT_LADDERS, LESSONS_BY_ID

LESSONS = tuple(LESSONS_BY_ID.values())

_LEGACY_SCHEMA_ONE_CHECKS = frozenset({"variables-v1", "conditions-v1"})


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _snapshot_schema_version(exercise_id: str, version: int, checks) -> int:
    """Use v1 only for the immutable legacy checks that predate choice feedback."""
    if not checks:
        return 2
    legacy_missing_choice_feedback = False
    question_ids: set[str] = set()
    for question in checks:
        if not isinstance(question, dict):
            raise ValueError("Exercise snapshot contains an invalid knowledge check")
        choices = question.get("choices")
        answer = question.get("answer")
        explanations = question.get("choice_explanations")
        if (
            not isinstance(question.get("id"), str)
            or not question["id"]
            or question["id"] in question_ids
            or not isinstance(question.get("prompt"), str)
            or not question["prompt"].strip()
            or not isinstance(choices, list)
            or not choices
            or not all(isinstance(choice, str) and choice for choice in choices)
            or len(set(choices)) != len(choices)
            or not isinstance(answer, str)
            or answer not in choices
            or not isinstance(question.get("explanation"), str)
            or not question["explanation"].strip()
        ):
            raise ValueError("Exercise snapshot contains an invalid knowledge check")
        question_ids.add(question["id"])
        if not (
            isinstance(explanations, dict)
            and set(explanations) == set(choices)
            and all(
                isinstance(explanations[choice], str)
                and explanations[choice].strip()
                for choice in choices
            )
        ):
            if exercise_id in _LEGACY_SCHEMA_ONE_CHECKS and version == 1:
                if explanations is not None:
                    raise ValueError("Legacy choice explanations are malformed")
                legacy_missing_choice_feedback = True
            else:
                raise ValueError("New knowledge checks require one explanation per choice")
    return 1 if legacy_missing_choice_feedback else 2


def validate_check_snapshot(snapshot: dict[str, Any], exercise_id: str) -> tuple[dict, ...]:
    """Validate a persisted check snapshot without consulting mutable authoring."""
    schema_version = snapshot.get("schema_version")
    checks = snapshot.get("checks")
    if (
        type(schema_version) is not int
        or schema_version not in {1, 2}
        or snapshot.get("exercise_id") != exercise_id
        or type(snapshot.get("version")) is not int
        or (
            schema_version == 1
            and (
                exercise_id not in _LEGACY_SCHEMA_ONE_CHECKS
                or snapshot.get("version") != 1
            )
        )
        or not isinstance(checks, list)
        or not checks
    ):
        raise ValueError("Exercise snapshot contains invalid knowledge checks")
    question_ids: set[str] = set()
    for question in checks:
        if not isinstance(question, dict):
            raise ValueError("Exercise snapshot contains invalid knowledge checks")
        question_id = question.get("id")
        choices = question.get("choices")
        answer = question.get("answer")
        explanation = question.get("explanation")
        if (
            not isinstance(question_id, str)
            or not question_id
            or question_id in question_ids
            or not isinstance(question.get("prompt"), str)
            or not question["prompt"].strip()
            or not isinstance(choices, list)
            or not choices
            or not all(isinstance(choice, str) and choice for choice in choices)
            or len(set(choices)) != len(choices)
            or not isinstance(answer, str)
            or answer not in choices
            or not isinstance(explanation, str)
            or not explanation.strip()
        ):
            raise ValueError("Exercise snapshot contains invalid knowledge checks")
        question_ids.add(question_id)
        if schema_version == 1 and "choice_explanations" in question:
            raise ValueError("Legacy schema cannot contain choice explanations")
        if schema_version == 2:
            explanations = question.get("choice_explanations")
            if (
                not isinstance(explanations, dict)
                or set(explanations) != set(choices)
                or not all(
                    isinstance(explanations[choice], str)
                    and explanations[choice].strip()
                    for choice in choices
                )
            ):
                raise ValueError("Exercise snapshot contains invalid knowledge checks")
    return tuple(checks)


def authored_snapshot(exercise_id: str) -> dict[str, Any]:
    authored = EXERCISE_HINT_LADDERS.get(exercise_id)
    lesson = next((item for item in LESSONS if item["id"] == exercise_id), None) or LESSONS_BY_ID.get(exercise_id)
    assessment = next((item for item in QUESTIONS if item["id"] == exercise_id), None) or QUESTIONS_BY_ID.get(exercise_id)
    if authored is None and assessment is None and lesson is None:
        raise ValueError("Exercise snapshot references unknown authored content")
    if authored is not None and authored.get("lesson_id") != exercise_id:
        raise ValueError("Exercise snapshot references an invalid hint ladder")
    if authored is not None and lesson is None:
        raise ValueError("Exercise snapshot references an unknown lesson")
    checks = CHECKS.get(exercise_id, ())
    if lesson is not None and not checks:
        raise ValueError("Lesson snapshot requires a knowledge check")
    version_number = authored["version"] if authored is not None else 1
    schema_version = _snapshot_schema_version(exercise_id, version_number, checks)
    snapshot = _clone(
        {
            "schema_version": schema_version,
            "exercise_id": exercise_id,
            "version": version_number,
            "lesson": lesson,
            "checks": checks,
            "assessment": assessment,
            "hints": [
                {"level": level, "kind": kind, "text": text}
                for level, kind, text in (authored["hints"] if authored is not None else ())
            ],
        }
    )
    if checks:
        validate_check_snapshot(snapshot, exercise_id)
    return snapshot


def snapshot_hints(snapshot: dict[str, Any]) -> tuple[tuple[int, str, str], ...]:
    return tuple(
        (item["level"], item["kind"], item["text"])
        for item in snapshot.get("hints", ())
    )


def snapshot_checks(snapshot: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple(snapshot.get("checks", ()))


def snapshot_assessment(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    assessment = snapshot.get("assessment")
    return assessment if isinstance(assessment, dict) else None


def snapshot_skill_id(
    snapshot: dict[str, Any] | None,
    *,
    exercise_id: str,
    version: int,
) -> str:
    """Return the primary skill from one immutable exercise snapshot.

    This helper intentionally never consults mutable authored content.  Coding
    evidence must fail closed when the persisted snapshot cannot prove the
    mapping.
    """
    if (
        not isinstance(snapshot, dict)
        or type(snapshot.get("schema_version")) is not int
        or snapshot.get("schema_version") not in {1, 2}
        or snapshot.get("exercise_id") != exercise_id
        or type(snapshot.get("version")) is not int
        or snapshot.get("version") != version
    ):
        raise ValueError("Exercise snapshot cannot prove its identity")

    lesson = snapshot.get("lesson")
    if isinstance(lesson, dict):
        skill_id = lesson.get("skill_id")
        if snapshot.get("kind") == "authored_python_function":
            from app.coding_exercises import contract_digest
            contract = snapshot.get("coding")
            if (not isinstance(contract, dict)
                or contract.get("exercise_id") != exercise_id
                or contract.get("version") != version
                or contract.get("lesson_id") != lesson.get("id")
                or contract.get("skill_id") != skill_id
                or not isinstance(skill_id, str) or not skill_id.strip()
                or not isinstance(contract.get("cases"), list) or not contract["cases"]):
                raise ValueError("Coding snapshot has no trusted skill mapping")
            try:
                valid_digest = contract_digest(contract) == snapshot.get("contract_digest")
            except (ValueError, TypeError):
                valid_digest = False
            if not valid_digest:
                raise ValueError("Coding snapshot contract is invalid")
            return skill_id
        if (
            lesson.get("id") != exercise_id
            or not isinstance(skill_id, str)
            or not skill_id.strip()
        ):
            raise ValueError("Exercise snapshot has no valid lesson skill mapping")
        return skill_id

    assessment = snapshot_assessment(snapshot)
    if isinstance(assessment, dict):
        skill_id = assessment.get("skill_id")
        if (
            assessment.get("id") != exercise_id
            or not isinstance(skill_id, str)
            or not skill_id.strip()
        ):
            raise ValueError("Exercise snapshot has no valid assessment skill mapping")
        return skill_id

    raise ValueError("Exercise snapshot has no primary skill mapping")
