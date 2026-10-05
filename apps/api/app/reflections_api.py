"""Owner scoped, version bound written practice without invented grades."""
from datetime import datetime
from hashlib import sha256
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import csrf_protected, current_auth
from app.db.models import AuthSession, ExerciseVersion, User
from app.db.reflection_models import LessonReflection
from app.db.session import get_db
from app.learning import accessible_lesson, _get_or_create_lesson_session

router = APIRouter(prefix="/learning/lessons", tags=["written-practice"])


class ReflectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=10000)


class ReflectionResponse(BaseModel):
    id: UUID
    lesson_id: str
    exercise_version: str
    text: str
    feedback: str
    created_at: datetime


def _response(db: Session, row: LessonReflection) -> ReflectionResponse:
    version = db.get(ExerciseVersion, row.exercise_version_id)
    if version is None:
        raise HTTPException(409, "Reflection content version is unavailable")
    return ReflectionResponse(
        id=row.id, lesson_id=row.lesson_id,
        exercise_version=f"{row.lesson_id}:{version.version}", text=row.text,
        feedback=row.feedback, created_at=row.created_at,
    )


@router.get("/{lesson_id}/reflections", response_model=list[ReflectionResponse])
def history(lesson_id: str, auth=Depends(current_auth), db: Session = Depends(get_db)):
    accessible_lesson(lesson_id, db, auth[0])
    rows = db.scalars(select(LessonReflection).where(
        LessonReflection.user_id == auth[0].id, LessonReflection.lesson_id == lesson_id,
    ).order_by(LessonReflection.created_at.desc()).limit(20)).all()
    return [_response(db, row) for row in rows]


@router.post("/{lesson_id}/reflections", response_model=ReflectionResponse, status_code=201)
def submit(
    lesson_id: str, payload: ReflectionRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db),
):
    user, _ = auth
    digest = sha256(idempotency_key.encode("utf-8")).hexdigest()
    existing = db.scalar(select(LessonReflection).where(
        LessonReflection.user_id == user.id, LessonReflection.idempotency_key == digest,
    ))
    if existing is not None:
        if existing.lesson_id != lesson_id or existing.text != payload.text:
            raise HTTPException(409, "Idempotency-Key was reused with different parameters")
        return _response(db, existing)
    accessible_lesson(lesson_id, db, user)
    _, version = _get_or_create_lesson_session(db, user, lesson_id)
    lesson = version.content_snapshot["lesson"]
    feedback = "Разбор сохранён. Он не оценивается автоматически и не меняет владение навыком. "
    conclusion = lesson.get("conclusion")
    if isinstance(conclusion, str) and conclusion.strip():
        feedback += f"Сравните своё объяснение с выводом урока: {conclusion[:4000]}"
    else:
        feedback += "Проверьте объяснение по теории и закрепите навык итоговой проверкой."
    row = LessonReflection(user_id=user.id, exercise_version_id=version.id,
                           lesson_id=lesson_id, idempotency_key=digest, text=payload.text, feedback=feedback)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(LessonReflection).where(
            LessonReflection.user_id == user.id, LessonReflection.idempotency_key == digest,
        ))
        if existing is None or existing.lesson_id != lesson_id or existing.text != payload.text:
            raise HTTPException(409, "Reflection could not be saved") from None
        row = existing
    db.refresh(row)
    return _response(db, row)
