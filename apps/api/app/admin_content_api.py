"""Read-only content administration.

The course is authored in code and published by review, so the admin surface does
not edit lessons at runtime: it answers what exists, whether it is complete, and
what a reviewer would see. That keeps one source of truth for the 90 lessons.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.accounts_api import admin_auth
from app.content_audit import report
from app.exercise_snapshots import authored_snapshot
from app.learning_content import LESSONS
from app.runner_exercise_content import RUNNER_EXERCISES

router = APIRouter(prefix="/admin/content", tags=["admin-content"])


@router.get("/overview")
def overview(auth=Depends(admin_auth)) -> dict:
    return report()


@router.get("/lessons")
def lessons(
    auth=Depends(admin_auth),
    phase: str | None = Query(default=None, max_length=40),
    query: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict:
    items = []
    for lesson in LESSONS:
        if phase and lesson.get("phase") != phase:
            continue
        if query and query.casefold() not in f"{lesson.get('title', '')} {lesson['id']}".casefold():
            continue
        items.append(
            {
                "id": lesson["id"],
                "title": lesson.get("title"),
                "skill_id": lesson.get("skill_id"),
                "phase": lesson.get("phase"),
                "practice": lesson.get("practice_submission_type"),
                "has_exercise": lesson["id"] + "-code" in RUNNER_EXERCISES,
            }
        )
        if len(items) >= limit:
            break
    return {"total": len(LESSONS), "returned": len(items), "lessons": items}


@router.get("/lessons/{lesson_id}")
def lesson_detail(lesson_id: str, auth=Depends(admin_auth)) -> dict:
    lesson = next((item for item in LESSONS if item["id"] == lesson_id), None)
    if lesson is None:
        raise HTTPException(404, "Lesson not found")
    try:
        snapshot = authored_snapshot(lesson_id)
    except ValueError:
        snapshot = {}
    checks = snapshot.get("checks") or []
    exercise = RUNNER_EXERCISES.get(lesson_id + "-code")
    return {
        "id": lesson["id"],
        "title": lesson.get("title"),
        "skill_id": lesson.get("skill_id"),
        "phase": lesson.get("phase"),
        "body_chars": len(lesson.get("body") or ""),
        "checks": [{"id": check["id"], "choices": len(check["choices"])} for check in checks],
        "exercise": (
            {
                "id": exercise["exercise_id"],
                "cases": len(exercise.get("tests") or []),
                "hidden": sum(1 for case in exercise.get("tests") or [] if case.get("visibility") == "hidden"),
                "hints": len(exercise.get("hints") or []),
            }
            if exercise
            else None
        ),
    }


@router.get("/exercises")
def exercises(auth=Depends(admin_auth)) -> dict:
    items = sorted(
        (
            {
                "id": row["exercise_id"],
                "lesson_id": row.get("lesson_id"),
                "cases": len(row.get("tests") or []),
                "hidden": sum(1 for case in row.get("tests") or [] if case.get("visibility") == "hidden"),
            }
            for row in RUNNER_EXERCISES.values()
        ),
        key=lambda item: item["id"],
    )
    return {"total": len(items), "exercises": items}
