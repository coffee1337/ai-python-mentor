from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import csrf_protected, current_auth
from app.db.models import AuthSession, LessonCompletion, MentorConversation, MentorMessage, User
from app.db.session import get_db
from app.learning_content import LESSONS

router = APIRouter(prefix="/learning", tags=["learning"])


class LessonSummary(BaseModel):
    id: str
    title: str
    minutes: int
    status: Literal["completed", "available", "locked"]
    completed_at: datetime | None = None


class LearningPath(BaseModel):
    title: str = "Первые шаги в Python"
    completed: int
    total: int
    next_lesson_id: str | None
    lessons: list[LessonSummary]


class LessonResponse(BaseModel):
    id: str
    title: str
    skill_id: str
    minutes: int
    body: str
    example: str
    question: str
    choices: list[str]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=200)


class AnswerResponse(BaseModel):
    correct: bool
    path: LearningPath


def require_onboarding(user: User) -> None:
    if user.profile is None or not user.profile.onboarding_completed:
        raise HTTPException(409, "Complete onboarding first")


def learning_path(db: Session, user: User) -> LearningPath:
    completions = {
        row.lesson_id: row.completed_at
        for row in db.scalars(select(LessonCompletion).where(LessonCompletion.user_id == user.id))
    }
    next_id = next((lesson["id"] for lesson in LESSONS if lesson["id"] not in completions), None)
    lessons = [
        LessonSummary(
            id=lesson["id"], title=lesson["title"], minutes=lesson["minutes"],
            status="completed" if lesson["id"] in completions else "available" if lesson["id"] == next_id else "locked",
            completed_at=completions.get(lesson["id"]),
        )
        for lesson in LESSONS
    ]
    return LearningPath(completed=sum(item.status == "completed" for item in lessons),
                        total=len(lessons), next_lesson_id=next_id, lessons=lessons)


def accessible_lesson(lesson_id: str, db: Session, user: User) -> dict:
    require_onboarding(user)
    lesson = next((item for item in LESSONS if item["id"] == lesson_id), None)
    if lesson is None:
        raise HTTPException(404, "Lesson not found")
    summary = next(item for item in learning_path(db, user).lessons if item.id == lesson_id)
    if summary.status == "locked":
        raise HTTPException(409, "Complete the previous lesson first")
    return lesson


@router.get("/path", response_model=LearningPath)
def get_path(auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    return learning_path(db, user)


@router.get("/next", response_model=LessonResponse | None)
def get_next(auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    next_id = learning_path(db, user).next_lesson_id
    return accessible_lesson(next_id, db, user) if next_id else None


@router.get("/lessons/{lesson_id}", response_model=LessonResponse)
def get_lesson(lesson_id: str, auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    return accessible_lesson(lesson_id, db, auth[0])


@router.post("/lessons/{lesson_id}/complete", response_model=AnswerResponse)
def complete_lesson(lesson_id: str, payload: AnswerRequest,
                    auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    user, _ = auth
    lesson = accessible_lesson(lesson_id, db, user)
    if payload.answer not in lesson["choices"]:
        raise HTTPException(422, "Choose one of the offered answers")
    correct = payload.answer == lesson["answer"]
    if correct and db.get(LessonCompletion, (user.id, lesson_id)) is None:
        db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
        assisted = db.scalar(select(MentorMessage.id).join(
            MentorConversation, MentorMessage.conversation_id == MentorConversation.id
        ).where(MentorConversation.user_id == user.id,
                MentorConversation.lesson_id == lesson_id,
                MentorMessage.role == "assistant").limit(1)) is not None
        db.add(LessonCompletion(user_id=user.id, lesson_id=lesson_id, answer=payload.answer,
                               evidence_type="authored_quiz_assisted" if assisted else "authored_quiz_correct"))
        try:
            db.commit()
        except IntegrityError:
            # Concurrent retries must not create duplicate evidence.
            db.rollback()
            if db.get(LessonCompletion, (user.id, lesson_id)) is None:
                raise
    return AnswerResponse(correct=correct, path=learning_path(db, user))
