from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import csrf_protected, current_auth
from app.db.models import AuthSession, ExerciseVersion, LearningPlan, LearningPlanItem, LessonCompletion, LessonSession, KnowledgeCheckSession, MentorConversation, MentorMessage, User, UserSkill, KnowledgeCheckAttempt, KnowledgeCheckResponse
from app.db.session import get_db
from app.learning_content import LESSONS, LESSONS_BY_ID
from app.backend_content import BACKEND_PHASES, BACKEND_PHASE_ONE_LESSONS
from app.skill_graph import seed_skill_graph
from app.curriculum import build_curriculum
from app.prerequisites import prerequisite_state
from app.db.models import LearningPlan, LearningPlanItem
from app.choice_order import ordered_choices

router = APIRouter(prefix="/learning", tags=["learning"])


class LessonSummary(BaseModel):
    id: str
    title: str
    minutes: int
    status: Literal["completed", "available", "locked"]
    completed_at: datetime | None = None
    phase: int | None = None


class PhaseSummary(BaseModel):
    """Course-phase progress derived from lesson facts, not mastery numbers."""

    id: int
    title: str
    summary: str
    status: Literal["completed", "available", "locked"]
    completed: int
    total: int
    next_lesson_id: str | None = None


class LearningPath(BaseModel):
    title: str = "Первые шаги в Python"
    completed: int
    total: int
    next_lesson_id: str | None
    lessons: list[LessonSummary]
    phases: list[PhaseSummary] = Field(default_factory=list)


class MisconceptionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    misconception: str
    prompt: str


class LessonCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str
    choices: list[str]


class LessonResponse(BaseModel):
    id: str
    title: str
    skill_id: str
    minutes: int
    body: str
    example: str
    question: str
    choices: list[str]
    # Structured lesson fields. The authored content carries these, but the
    # response used to truncate to the eight fields above, which collapsed the
    # goal/theory/checkpoint/practice structure into one opaque `body` blob.
    goal: str | None = None
    theory: str | None = None
    conclusion: str | None = None
    example_output: str | None = None
    checkpoint: LessonCheckpoint | None = None
    # Authored as {"misconception": ..., "prompt": ...}; flattened to strings
    # because the response exposed only `misconception` before.
    misconception_check: MisconceptionCheck | None = None
    misconception: str | None = None
    practice: str | None = None
    prerequisites: list[str] = Field(default_factory=list)
    difficulty: int | None = None
    phase: int | None = None
    version: str | None = None


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=200)


class AnswerResponse(BaseModel):
    correct: bool
    path: LearningPath


def require_onboarding(user: User) -> None:
    if user.profile is None or not user.profile.onboarding_completed:
        raise HTTPException(409, "Complete onboarding first")


def _invalid_lesson_snapshot() -> HTTPException:
    return HTTPException(409, "Lesson content snapshot is unavailable")


def _lesson_from_snapshot(version: ExerciseVersion, lesson_id: str) -> dict[str, Any]:
    snapshot = version.content_snapshot
    lesson = snapshot.get("lesson") if isinstance(snapshot, dict) else None
    choices = lesson.get("choices") if isinstance(lesson, dict) else None
    if (
        version.exercise_id != lesson_id
        or version.lesson_id != lesson_id
        or not isinstance(snapshot, dict)
        or snapshot.get("schema_version") not in {1, 2}
        or snapshot.get("exercise_id") != lesson_id
        or snapshot.get("version") != version.version
        or not isinstance(lesson, dict)
        or lesson.get("id") != lesson_id
        or not isinstance(lesson.get("title"), str)
        or not isinstance(lesson.get("skill_id"), str)
        or not isinstance(lesson.get("minutes"), int)
        or isinstance(lesson.get("minutes"), bool)
        or lesson["minutes"] <= 0
        or not isinstance(lesson.get("body"), str)
        or not isinstance(lesson.get("example"), str)
        or not isinstance(lesson.get("question"), str)
        or not isinstance(choices, list)
        or not choices
        or not all(isinstance(choice, str) for choice in choices)
        or not isinstance(lesson.get("answer"), str)
        or lesson["answer"] not in choices
    ):
        raise _invalid_lesson_snapshot()
    return lesson


def _lesson_response(version: ExerciseVersion, lesson_id: str, session_id) -> dict[str, Any]:
    lesson = dict(_lesson_from_snapshot(version, lesson_id))
    lesson["version"] = str(version.version)
    lesson["choices"] = ordered_choices(lesson["choices"], session_id=session_id, question_id=lesson_id)
    checkpoint = lesson.get("checkpoint")
    if isinstance(checkpoint, dict):
        checkpoint = dict(checkpoint)
        # imports-v1 was published with one string instead of a list. Adapt
        # the public shape only; its immutable snapshot and grading stay intact.
        choices = checkpoint.get("choices")
        if isinstance(choices, str):
            choices = [choices]
        if isinstance(choices, list):
            checkpoint["choices"] = ordered_choices(choices, session_id=session_id, question_id=f"{lesson_id}:checkpoint")
        lesson["checkpoint"] = checkpoint
    return lesson


def _persisted_lesson(lesson_id: str, db: Session) -> dict[str, Any]:
    return _lesson_from_snapshot(_persisted_lesson_version(lesson_id, db), lesson_id)


def _persisted_lesson_version(lesson_id: str, db: Session) -> ExerciseVersion:
    if lesson_id not in LESSONS_BY_ID:
        raise HTTPException(404, "Lesson not found")

    # Keep the import local: exercise_hints uses accessible_lesson for its
    # endpoint, so importing it at module load time would create a cycle.
    from app.exercise_hints import _seed_exercise

    try:
        return _seed_exercise(db, lesson_id, seed_hints=False)
    except ValueError as exc:
        raise HTTPException(404, "Lesson not found") from exc


def _pending_lesson_session(db: Session, user_id, lesson_id: str) -> LessonSession | None:
    return db.scalar(
        select(LessonSession)
        .where(
            LessonSession.user_id == user_id,
            LessonSession.lesson_id == lesson_id,
            LessonSession.consumed_at.is_(None),
        )
        .order_by(LessonSession.created_at.desc())
        .limit(1)
    )


def _pending_knowledge_check_session(
    db: Session, user_id, lesson_id: str
) -> KnowledgeCheckSession | None:
    return db.scalar(
        select(KnowledgeCheckSession)
        .where(
            KnowledgeCheckSession.user_id == user_id,
            KnowledgeCheckSession.lesson_id == lesson_id,
            KnowledgeCheckSession.consumed_at.is_(None),
        )
        .order_by(KnowledgeCheckSession.created_at.desc())
        .limit(1)
    )


def _lesson_session_version(db: Session, session: LessonSession, lesson_id: str) -> ExerciseVersion:
    version = db.get(ExerciseVersion, session.exercise_version_id)
    if version is None or version.lesson_id != lesson_id:
        raise HTTPException(409, "Lesson exercise version is unavailable")
    _lesson_from_snapshot(version, lesson_id)
    return version


def _get_or_create_lesson_session(
    db: Session, user: User, lesson_id: str,
) -> tuple[LessonSession, ExerciseVersion]:
    session = _pending_lesson_session(db, user.id, lesson_id)
    if session is not None:
        return session, _lesson_session_version(db, session, lesson_id)

    version = _persisted_lesson_version(lesson_id, db)
    session = LessonSession(
        user_id=user.id,
        lesson_id=lesson_id,
        exercise_version_id=version.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        session = _pending_lesson_session(db, user.id, lesson_id)
        if session is None:
            raise HTTPException(409, "Lesson session could not be created")
        version = _lesson_session_version(db, session, lesson_id)
    return session, version


def learning_path(db: Session, user: User) -> LearningPath:
    seed_skill_graph(db)
    readiness = prerequisite_state(db, user.id)
    completions = {
        row.lesson_id: row.completed_at
        for row in db.scalars(select(LessonCompletion).where(LessonCompletion.user_id == user.id))
    }
    for old_id, new_id in {"imports-v1": "imports-v2", "fixtures-v1": "fixtures-v2"}.items():
        if old_id in completions and new_id not in completions:
            completions[new_id] = completions[old_id]
    plan = db.scalar(select(LearningPlan).where(LearningPlan.user_id == user.id))
    ordered_lessons = []
    for item in LESSONS:
        lesson_id = item["id"]
        lesson_session = _pending_lesson_session(db, user.id, lesson_id)
        if lesson_session is not None:
            lesson = _lesson_from_snapshot(
                _lesson_session_version(db, lesson_session, lesson_id), lesson_id
            )
        else:
            check_session = _pending_knowledge_check_session(
                db, user.id, lesson_id
            )
            if check_session is not None:
                check_version = db.get(ExerciseVersion, check_session.exercise_version_id)
                if check_version is None or check_version.lesson_id != lesson_id:
                    raise HTTPException(409, "Knowledge-check exercise version is unavailable")
                lesson = _lesson_from_snapshot(check_version, lesson_id)
            else:
                lesson = _persisted_lesson(lesson_id, db)
        ordered_lessons.append(lesson)
    if plan is not None:
        order = {item.lesson_id: item.position for item in db.scalars(select(LearningPlanItem).where(LearningPlanItem.plan_id == plan.id)).all()}
        ordered_lessons.sort(key=lambda lesson: order.get(lesson["id"], len(order) + 1))
    def ready(lesson: dict) -> bool:
        return readiness.is_lesson_ready(lesson)

    next_id = next((lesson["id"] for lesson in ordered_lessons
                    if lesson["id"] not in completions and ready(lesson)), None)
    def phase_of(lesson: dict) -> int | None:
        return lesson.get("phase")

    lessons = [
        LessonSummary(
            id=lesson["id"], title=lesson["title"], minutes=lesson["minutes"],
            status="completed" if lesson["id"] in completions else "available" if ready(lesson) else "locked",
            completed_at=completions.get(lesson["id"]),
            phase=phase_of(lesson),
        )
        for lesson in ordered_lessons
    ]
    phases = _phase_summaries(lessons)
    return LearningPath(completed=sum(item.status == "completed" for item in lessons),
                        total=len(lessons), next_lesson_id=next_id, lessons=lessons,
                        phases=phases)


def _phase_summaries(lessons: list[LessonSummary]) -> list[PhaseSummary]:
    """Describe each authored backend phase by lesson completion counts.

    A phase is reported as completed only when every published lesson in it is
    completed, and as available only when at least one of its lessons is
    reachable. Progress is expressed as counts of finished lessons, never as a
    mastery percentage.
    """
    by_id = {lesson.id: lesson for lesson in lessons}
    phase_of_skill = {
        skill_id: phase["id"]
        for phase in BACKEND_PHASES
        for skill_id in phase["skill_ids"]
    }
    published: dict[int, list[LessonSummary]] = {}
    for lesson in LESSONS:
        summary = by_id.get(lesson["id"])
        phase_id = phase_of_skill.get(lesson["skill_id"])
        if summary is not None and phase_id is not None:
            published.setdefault(phase_id, []).append(summary)
    summaries: list[PhaseSummary] = []
    blocked = False
    for phase in BACKEND_PHASES:
        items = published.get(phase["id"], [])
        if not items:
            # Not published yet: the learner must not see an empty gate.
            continue
        completed = sum(item.status == "completed" for item in items)
        available = [item for item in items if item.status == "available"]
        if completed == len(items):
            status = "completed"
        elif available and not blocked:
            status = "available"
        else:
            status = "locked"
        if status != "completed":
            blocked = True
        summaries.append(
            PhaseSummary(
                id=phase["id"],
                title=phase["title"],
                summary=phase["summary"],
                status=status,
                completed=completed,
                total=len(items),
                next_lesson_id=available[0].id if status == "available" and available else None,
            )
        )
    return summaries


def accessible_lesson(
    lesson_id: str,
    db: Session,
    user: User,
    *,
    bound_version: ExerciseVersion | None = None,
) -> dict:
    require_onboarding(user)
    bound_pending_flow = False
    if bound_version is not None:
        bound_lesson_session = db.scalar(
            select(LessonSession.id).where(
                LessonSession.user_id == user.id,
                LessonSession.lesson_id == lesson_id,
                LessonSession.exercise_version_id == bound_version.id,
                LessonSession.consumed_at.is_(None),
            )
        )
        bound_check_session = db.scalar(
            select(KnowledgeCheckSession.id).where(
                KnowledgeCheckSession.user_id == user.id,
                KnowledgeCheckSession.lesson_id == lesson_id,
                KnowledgeCheckSession.exercise_version_id == bound_version.id,
                KnowledgeCheckSession.consumed_at.is_(None),
            )
        )
        if bound_lesson_session is None and bound_check_session is None:
            raise HTTPException(409, "Lesson session is unavailable")
        bound_pending_flow = True
        lesson = _lesson_from_snapshot(bound_version, lesson_id)
    else:
        session = _pending_lesson_session(db, user.id, lesson_id)
        lesson = (
            _lesson_from_snapshot(_lesson_session_version(db, session, lesson_id), lesson_id)
            if session else _persisted_lesson(lesson_id, db)
        )
    summary = next((item for item in learning_path(db, user).lessons if item.id == lesson_id), None)
    # Historical publications remain readable/finishable under the same
    # prerequisite policy even after their replacement becomes active.
    locked = summary.status == "locked" if summary is not None else not prerequisite_state(db, user.id).is_lesson_ready(lesson)
    if locked and not bound_pending_flow:
        raise HTTPException(409, "Complete prerequisite lessons first")
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
    if not next_id:
        return None
    accessible_lesson(next_id, db, user)
    session, version = _get_or_create_lesson_session(db, user, next_id)
    db.commit()
    return _lesson_response(version, next_id, session.id)


@router.get("/lessons/{lesson_id}", response_model=LessonResponse)
def get_lesson(lesson_id: str, auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    user = auth[0]
    pending = _pending_lesson_session(db, user.id, lesson_id)
    if pending is not None:
        accessible_lesson(
            lesson_id, db, user, bound_version=_lesson_session_version(db, pending, lesson_id)
        )
    else:
        accessible_lesson(lesson_id, db, user)
    session, version = _get_or_create_lesson_session(db, user, lesson_id)
    db.commit()
    return _lesson_response(version, lesson_id, session.id)


@router.post("/lessons/{lesson_id}/complete", response_model=AnswerResponse)
def complete_lesson(lesson_id: str, payload: AnswerRequest,
                    auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    session = _pending_lesson_session(db, user.id, lesson_id)
    if session is not None:
        # Bind first, then authorize against the same immutable snapshot.
        version = _lesson_session_version(db, session, lesson_id)
        accessible_lesson(lesson_id, db, user, bound_version=version)
    else:
        if db.scalar(select(LessonSession.id).where(
            LessonSession.user_id == user.id, LessonSession.lesson_id == lesson_id,
        ).limit(1)) is not None:
            raise HTTPException(409, "Get the lesson before submitting again")
        # Direct POST may bind only on a flow that has never had a GET.
        accessible_lesson(lesson_id, db, user)
        session, version = _get_or_create_lesson_session(db, user, lesson_id)
    lesson = _lesson_from_snapshot(version, lesson_id)
    if payload.answer not in lesson["choices"]:
        raise HTTPException(422, "Choose one of the offered answers")
    correct = payload.answer == lesson["answer"]
    completion = db.get(LessonCompletion, (user.id, lesson_id))
    if correct and completion is None:
        assisted = db.scalar(select(MentorMessage.id).join(
            MentorConversation, MentorMessage.conversation_id == MentorConversation.id
        ).where(MentorConversation.user_id == user.id,
                MentorConversation.lesson_id == lesson_id,
                MentorMessage.role == "assistant").limit(1)) is not None
        db.add(LessonCompletion(user_id=user.id, lesson_id=lesson_id, answer=payload.answer,
                               exercise_version_id=version.id,
                               evidence_type="authored_quiz_assisted" if assisted else "authored_quiz_correct"))
        if session is not None:
            session.consumed_at = datetime.now(timezone.utc)
        try:
            build_curriculum(db, user, reason="lesson_completed")
            db.commit()
        except IntegrityError:
            # Concurrent retries must not create duplicate evidence.
            db.rollback()
            if db.get(LessonCompletion, (user.id, lesson_id)) is None:
                raise
    elif correct and session is not None:
        session.consumed_at = datetime.now(timezone.utc)
        db.commit()
    elif not correct and session is not None:
        db.commit()
    return AnswerResponse(correct=correct, path=learning_path(db, user))
