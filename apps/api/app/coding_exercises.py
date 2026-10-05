"""Publish and authorize trusted authored coding contracts separately from quizzes."""
from copy import deepcopy
from hashlib import sha256
import json
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.db.models import ExerciseVersion
from app.learning import accessible_lesson


def contract_digest(contract: dict) -> str:
    return sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def validate_coding_snapshot(version: ExerciseVersion) -> dict:
    snapshot = version.content_snapshot
    contract = snapshot.get("coding") if isinstance(snapshot, dict) else None
    lesson = snapshot.get("lesson") if isinstance(snapshot, dict) else None
    if (not isinstance(snapshot, dict) or snapshot.get("schema_version") != 2
        or snapshot.get("kind") != "authored_python_function"
        or snapshot.get("exercise_id") != version.exercise_id
        or snapshot.get("version") != version.version
        or not isinstance(contract, dict) or not isinstance(lesson, dict)
        or contract.get("exercise_id") != version.exercise_id
        or contract.get("version") != version.version
        or contract.get("lesson_id") != version.lesson_id
        or lesson.get("id") != version.lesson_id
        or contract.get("skill_id") != lesson.get("skill_id")
        or not isinstance(contract.get("skill_id"), str)
        or not isinstance(contract.get("cases"), list)
        or not 2 <= len(contract["cases"]) <= 100
    ):
        raise HTTPException(409, "Coding exercise version is unavailable")
    try:
        digest = contract_digest(contract)
    except (ValueError, TypeError):
        raise HTTPException(409, "Coding exercise contract is invalid") from None
    if snapshot.get("contract_digest") != digest:
        raise HTTPException(409, "Coding exercise contract is invalid")
    if not all(isinstance(case, dict) and isinstance(case.get("args"), list)
               and isinstance(case.get("kwargs"), dict) and "expected" in case
               and case.get("visibility") in {"public", "hidden"} for case in contract["cases"]):
        raise HTTPException(409, "Coding exercise contract is invalid")
    return contract


def resolve_coding_exercise(db, user, exercise_id: str, *, bound_version: ExerciseVersion | None = None):
    """Return (immutable internal contract, version); never expose the first to clients."""
    if bound_version is not None:
        if bound_version.exercise_id != exercise_id:
            raise HTTPException(409, "Coding exercise binding does not match")
        contract = validate_coding_snapshot(bound_version)
        accessible_lesson(contract["lesson_id"], db, user)
        return contract, bound_version
    from app.runner_exercise_content import RUNNER_EXERCISES
    item = RUNNER_EXERCISES.get(exercise_id)
    if item is None:
        raise HTTPException(404, "Coding exercise not found")
    accessible_lesson(item["lesson_id"], db, user)
    version = db.scalar(select(ExerciseVersion).where(
        ExerciseVersion.exercise_id == exercise_id, ExerciseVersion.version == item["version"],
    ))
    if version is not None:
        return validate_coding_snapshot(version), version
    contract = deepcopy(item)
    # This mapping is deliberately minimal. Lesson theory belongs to the
    # lesson's own immutable version; coding hints and tests belong here.
    snapshot = {
        "schema_version": 2, "kind": "authored_python_function",
        "exercise_id": exercise_id, "version": item["version"],
        "lesson": {"id": item["lesson_id"], "skill_id": item["skill_id"]},
        "coding": contract, "contract_digest": contract_digest(contract),
        "checks": [], "assessment": None,
        "hints": [{"level": level, "kind": kind, "text": text} for level, kind, text in item.get("hints", ())],
    }
    version = ExerciseVersion(exercise_id=exercise_id, version=item["version"],
                              lesson_id=item["lesson_id"], content_snapshot=snapshot)
    try:
        with db.begin_nested():
            db.add(version)
            db.flush()
    except IntegrityError:
        version = db.scalar(select(ExerciseVersion).where(
            ExerciseVersion.exercise_id == exercise_id, ExerciseVersion.version == item["version"],
        ))
        if version is None:
            raise
    return validate_coding_snapshot(version), version
