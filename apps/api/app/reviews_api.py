"""Authenticated API for server-graded delayed reviews."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from hashlib import sha256

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import csrf_protected, current_auth
from app.curriculum import build_curriculum
from app.db.models import (
    AuthSession,
    ExerciseVersion,
    ReviewAttempt,
    ReviewSession,
    SkillEvidence,
    User,
    UserSkill,
)
from app.db.session import get_db
from app.exercise_hints import _seed_exercise
from app.exercise_snapshots import snapshot_assessment
from app.learning import require_onboarding
from app.learning_content import LESSONS
from app.reviews import record_review_attempt
from app.schemas import (
    ReviewTodayCompleteRequest,
    ReviewTodayCompleteResponse,
    ReviewTodayItem,
    ReviewTodayQuestion,
    ReviewTodayResponse,
)
from app.security import new_token, token_digest
from app.skill_evidence import InvalidEvidence
from app.choice_order import ordered_choices


router = APIRouter(prefix="/learning/reviews", tags=["reviews"])


class ReviewQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=4000)
    choices: list[str] = Field(min_length=1, max_length=8)


class DueReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(min_length=1, max_length=120)
    scheduled_for: date
    overdue_days: int = Field(ge=0, le=36500)


class DueReviewsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DueReviewItem] = Field(max_length=100)


class StartReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(min_length=1, max_length=120)


class StartReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_token: str = Field(min_length=32, max_length=200)
    skill_id: str = Field(min_length=1, max_length=120)
    scheduled_for: date
    question: ReviewQuestion
    questions: list[ReviewQuestion] = Field(min_length=1, max_length=20)


class AnswerReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_token: str = Field(min_length=32, max_length=200)
    answer: str | None = Field(default=None, min_length=1, max_length=200)
    answers: dict[str, str] | None = None

    @model_validator(mode="after")
    def validate_answer_shape(self):
        if (self.answer is None) == (self.answers is None):
            raise ValueError("Send exactly one answer or answers map")
        if self.answers is not None:
            if not 1 <= len(self.answers) <= 20:
                raise ValueError("Answers are invalid")
            if any(not isinstance(key, str) or not 1 <= len(key) <= 100 for key in self.answers):
                raise ValueError("Answers are invalid")
            if any(not isinstance(value, str) or not 1 <= len(value) <= 200 for value in self.answers.values()):
                raise ValueError("Answers are invalid")
        return self


class AnswerReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correct: bool
    score: float = Field(ge=0, le=1)
    scheduled_for: date
    next_review_at: datetime | None = None
    assisted: bool
    hint_count: int = Field(ge=0, le=5)
    interval_days: int | None = Field(default=None, ge=1, le=60)
    replayed: bool = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _lesson_for_skill(skill_id: str) -> dict | None:
    return next((lesson for lesson in LESSONS if lesson["skill_id"] == skill_id), None)


def _public_sources(version: ExerciseVersion, skill_id: str) -> list[dict]:
    snapshot = version.content_snapshot
    lesson = snapshot.get("lesson") if isinstance(snapshot, dict) else None
    assessment = snapshot_assessment(snapshot) if isinstance(snapshot, dict) else None
    if isinstance(lesson, dict):
        if lesson.get("id") != version.exercise_id or lesson.get("skill_id") != skill_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Review content snapshot is unavailable")
        checks = snapshot.get("checks", ()) if isinstance(snapshot, dict) else ()
        sources = list(checks) if checks else [lesson]
    elif isinstance(assessment, dict):
        sources = [assessment]
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "Review content snapshot is unavailable")
    if not sources or len(sources) > 20:
        raise HTTPException(status.HTTP_409_CONFLICT, "Review content snapshot is unavailable")
    for source in sources:
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("id"), str)
            or not 1 <= len(source["id"]) <= 100
            or not isinstance(source.get("prompt", source.get("question")), str)
            or not isinstance(source.get("choices"), list)
            or not 1 <= len(source["choices"]) <= 8
            or any(not isinstance(choice, str) or not choice for choice in source["choices"])
            or not isinstance(source.get("answer"), str)
            or source["answer"] not in source["choices"]
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Review content snapshot is unavailable")
    return sources


def _public_questions(version: ExerciseVersion, skill_id: str, session_id) -> list[ReviewQuestion]:
    return [
        ReviewQuestion(
            id=source["id"],
            prompt=source.get("prompt", source.get("question")),
            choices=ordered_choices(source["choices"],session_id=session_id,question_id=source["id"]),
        )
        for source in _public_sources(version, skill_id)
    ]


def _due_rows(db: Session, user: User, *, now: datetime | None = None) -> list[tuple[UserSkill, datetime]]:
    current = now or _utc_now()
    rows = db.scalars(
        select(UserSkill)
        .where(UserSkill.user_id == user.id, UserSkill.next_review_at.is_not(None))
        .order_by(UserSkill.next_review_at.asc(), UserSkill.skill_id.asc())
    ).all()
    result: list[tuple[UserSkill, datetime]] = []
    for row in rows:
        assert row.next_review_at is not None
        due_at = _as_utc(row.next_review_at)
        if due_at <= current and _lesson_for_skill(row.skill_id) is not None:
            result.append((row, due_at))
    return result


def _find_session_for_token(db: Session, user: User, token: str) -> ReviewSession | None:
    return db.scalar(
        select(ReviewSession).where(
            ReviewSession.user_id == user.id,
            ReviewSession.token_hash == token_digest(token),
        )
    )


def _get_or_create_session(
    db: Session,
    user: User,
    skill_id: str,
    due_at: datetime,
    *,
    reuse_completed: bool = False,
) -> tuple[ReviewSession, str]:
    scheduled_for = due_at.date()
    query = select(ReviewSession).where(
        ReviewSession.user_id == user.id,
        ReviewSession.skill_id == skill_id,
        ReviewSession.scheduled_for == scheduled_for,
    )
    if not reuse_completed:
        query = query.where(ReviewSession.completed_at.is_(None))
    existing = db.scalar(query)
    if existing is not None:
        # A due item may still be available after a same-day observation whose
        # schedule was intentionally not shifted. Rebind the day's session to a
        # fresh opaque token; ReviewAttempt remains the append-only history.
        if existing.completed_at is not None:
            existing.completed_at = None
        raw_token = new_token()
        existing.token_hash = token_digest(raw_token)
        db.flush()
        return existing, raw_token

    lesson = _lesson_for_skill(skill_id)
    if lesson is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No review exercise is available for this skill")
    try:
        version = _seed_exercise(db, lesson["id"])
        _public_sources(version, skill_id)
        raw_token = new_token()
        session = ReviewSession(
            user_id=user.id,
            skill_id=skill_id,
            exercise_version_id=version.id,
            scheduled_for=scheduled_for,
            token_hash=token_digest(raw_token),
        )
        db.add(session)
        db.flush()
        return session, raw_token
    except IntegrityError:
        db.rollback()
        query = select(ReviewSession).where(
            ReviewSession.user_id == user.id,
            ReviewSession.skill_id == skill_id,
            ReviewSession.scheduled_for == scheduled_for,
        )
        if not reuse_completed:
            query = query.where(ReviewSession.completed_at.is_(None))
        existing = db.scalar(query)
        if existing is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Review session could not be created")
        if existing.completed_at is not None:
            existing.completed_at = None
        raw_token = new_token()
        existing.token_hash = token_digest(raw_token)
        db.flush()
        return existing, raw_token


@router.get("/due", response_model=DueReviewsResponse)
def due_reviews(
    auth: tuple[User, AuthSession] = Depends(current_auth),
    db: Session = Depends(get_db),
) -> DueReviewsResponse:
    user, _ = auth
    require_onboarding(user)
    now = _utc_now()
    return DueReviewsResponse(
        items=[
            DueReviewItem(
                skill_id=row.skill_id,
                scheduled_for=due_at.date(),
                overdue_days=max(0, (now.date() - due_at.date()).days),
            )
            for row, due_at in _due_rows(db, user, now=now)
        ]
    )


@router.get("/today", response_model=ReviewTodayResponse)
def reviews_today(
    auth: tuple[User, AuthSession] = Depends(current_auth),
    db: Session = Depends(get_db),
) -> ReviewTodayResponse:
    """Return due and overdue authored review prompts bound to immutable versions."""
    user, _ = auth
    require_onboarding(user)
    now = _utc_now()
    items: list[ReviewTodayItem] = []
    for row, due_at in _due_rows(db, user, now=now):
        session, raw_token = _get_or_create_session(
            db, user, row.skill_id, due_at, reuse_completed=True
        )
        version = db.get(ExerciseVersion, session.exercise_version_id)
        if version is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Review content snapshot is unavailable",
            )
        questions = _public_questions(version, session.skill_id, session.id)
        items.append(
            ReviewTodayItem(
                review_token=raw_token,
                skill_id=session.skill_id,
                scheduled_for=session.scheduled_for,
                overdue_days=max(0, (now.date() - due_at.date()).days),
                questions=[
                    ReviewTodayQuestion(
                        id=question.id,
                        prompt=question.prompt,
                        choices=question.choices,
                    )
                    for question in questions
                ],
            )
        )
    db.commit()
    return ReviewTodayResponse(as_of=now, items=items)


@router.post("/today/complete", response_model=ReviewTodayCompleteResponse)
def complete_review_today(
    payload: ReviewTodayCompleteRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=200,
    ),
    auth: tuple[User, AuthSession] = Depends(csrf_protected),
    db: Session = Depends(get_db),
) -> ReviewTodayCompleteResponse:
    """Grade a submitted answer map against the session's immutable snapshot."""
    user, _ = auth
    require_onboarding(user)
    if not idempotency_key.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Idempotency-Key header is required",
        )
    session = _find_session_for_token(db, user, payload.review_token)
    if session is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Review session is unavailable")
    version = db.get(ExerciseVersion, session.exercise_version_id)
    if version is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Review content snapshot is unavailable",
        )

    sources = _public_sources(version, session.skill_id)
    expected = {source["id"]: source for source in sources}
    answer_map = dict(payload.answers)
    if set(answer_map) != set(expected):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Answer every public review question exactly once",
        )
    if any(
        answer not in expected[question_id]["choices"]
        for question_id, answer in answer_map.items()
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Choose one of the offered answers",
        )

    correct_count = sum(
        answer_map[question_id] == source["answer"]
        for question_id, source in expected.items()
    )
    score = correct_count / len(expected)
    canonical_answers = {key: answer_map[key] for key in sorted(answer_map)}
    persisted_key = "review-today:" + idempotency_key.strip()
    request_hash = "sha256:" + sha256(persisted_key.encode("utf-8")).hexdigest()
    replay = db.scalar(
        select(ReviewAttempt.id).where(
            ReviewAttempt.user_id == user.id,
            ReviewAttempt.idempotency_key == request_hash,
        )
    ) is not None

    try:
        attempt = record_review_attempt(
            db,
            user_id=user.id,
            review_session_id=session.id,
            result_score=score,
            idempotency_key=persisted_key,
            answers=canonical_answers,
        )
        evidence = db.get(SkillEvidence, attempt.skill_evidence_id)
        mastery = db.scalar(
            select(UserSkill).where(
                UserSkill.user_id == user.id,
                UserSkill.skill_id == attempt.skill_id,
            )
        )
        if evidence is None or not evidence.retention_only or mastery is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Review result is unavailable",
            )
        policy = (
            evidence.evidence_metadata.get("review_policy", {})
            if isinstance(evidence.evidence_metadata, dict)
            else {}
        )
        if not isinstance(policy, dict) or not isinstance(
            policy.get("schedule_applied"), bool
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Review result is unavailable",
            )
        if not replay:
            build_curriculum(db, user, reason="review")
        db.commit()
    except InvalidEvidence as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Review could not be recorded",
        ) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Review could not be recorded",
        ) from exc
    except HTTPException:
        db.rollback()
        raise

    result_score = float(evidence.result_score)
    outcome = (
        "correct"
        if result_score >= 1.0
        else "partial"
        if result_score > 0.0
        else "incorrect"
    )
    return ReviewTodayCompleteResponse(
        status="replayed" if replay else "recorded",
        outcome=outcome,
        schedule_applied=policy["schedule_applied"],
        same_day=not policy["schedule_applied"],
        next_review_at=(
            _as_utc(mastery.next_review_at)
            if mastery.next_review_at is not None
            else None
        ),
    )


@router.post("/session/start", response_model=StartReviewResponse, status_code=status.HTTP_201_CREATED)
def start_review_session(
    payload: StartReviewRequest,
    auth: tuple[User, AuthSession] = Depends(csrf_protected),
    db: Session = Depends(get_db),
) -> StartReviewResponse:
    user, _ = auth
    require_onboarding(user)
    due = next((item for item in _due_rows(db, user) if item[0].skill_id == payload.skill_id), None)
    if due is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Review is not due")
    row, due_at = due
    session, raw_token = _get_or_create_session(db, user, row.skill_id, due_at)
    version = db.get(ExerciseVersion, session.exercise_version_id)
    if version is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Review content snapshot is unavailable")
    questions = _public_questions(version, session.skill_id, session.id)
    db.commit()
    return StartReviewResponse(
        session_token=raw_token,
        skill_id=session.skill_id,
        scheduled_for=session.scheduled_for,
        question=questions[0],
        questions=questions,
    )


@router.post("/answer", response_model=AnswerReviewResponse)
def answer_review(
    payload: AnswerReviewRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=200),
    auth: tuple[User, AuthSession] = Depends(csrf_protected),
    db: Session = Depends(get_db),
) -> AnswerReviewResponse:
    user, _ = auth
    require_onboarding(user)
    session = _find_session_for_token(db, user, payload.session_token)
    if session is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Review session is unavailable")
    version = db.get(ExerciseVersion, session.exercise_version_id)
    if version is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Review content snapshot is unavailable")
    sources = _public_sources(version, session.skill_id)
    expected = {source["id"]: source for source in sources}
    if payload.answers is None:
        if len(expected) != 1:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Answer all public review questions")
        answer_map = {next(iter(expected)): payload.answer}
    else:
        answer_map = dict(payload.answers)
    if set(answer_map) != set(expected):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Answer every public review question exactly once")
    if any(answer not in expected[question_id]["choices"] for question_id, answer in answer_map.items()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose one of the offered answers")

    correct_count = sum(answer_map[question_id] == source["answer"] for question_id, source in expected.items())
    score = correct_count / len(expected)
    canonical_answers = {key: answer_map[key] for key in sorted(answer_map)}
    raw_key = idempotency_key or "review:" + sha256(json.dumps(canonical_answers, sort_keys=True).encode("utf-8")).hexdigest()
    if len(raw_key) > 240:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Idempotency-Key is too long")
    persisted_key = "review:" + raw_key
    request_hash = "sha256:" + sha256(persisted_key.encode("utf-8")).hexdigest()
    replay = db.scalar(
        select(ReviewAttempt).where(
            ReviewAttempt.user_id == user.id,
            ReviewAttempt.idempotency_key == request_hash,
        )
    ) is not None
    try:
        attempt = record_review_attempt(
            db,
            user_id=user.id,
            review_session_id=session.id,
            result_score=score,
            idempotency_key=persisted_key,
            answers=canonical_answers,
        )
        if not replay:
            build_curriculum(db, user, reason="review")
        evidence = db.get(SkillEvidence, attempt.skill_evidence_id)
        mastery = db.scalar(
            select(UserSkill).where(
                UserSkill.user_id == user.id,
                UserSkill.skill_id == attempt.skill_id,
            )
        )
        if evidence is None or mastery is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Review result is unavailable")
        db.commit()
    except InvalidEvidence as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Review could not be recorded") from exc
    except HTTPException:
        db.rollback()
        raise

    policy = evidence.evidence_metadata.get("review_policy", {}) if isinstance(evidence.evidence_metadata, dict) else {}
    return AnswerReviewResponse(
        correct=float(evidence.result_score) >= 1.0,
        score=float(evidence.result_score),
        scheduled_for=attempt.scheduled_for,
        next_review_at=mastery.next_review_at,
        assisted=bool(evidence.assisted),
        hint_count=int(evidence.hint_count),
        interval_days=policy.get("interval_days"),
        replayed=replay,
    )
