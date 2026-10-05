"""Domain service for recording delayed-review retention observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from typing import Sequence
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ReviewAttempt, ReviewSession, SkillEvidence, User
from app.skill_evidence import (
    InvalidEvidence,
    _record_review_evidence,
    derive_review_assistance,
)


REVIEW_POLICY_VERSION = "review-v1"
_REVIEW_INTERVALS_DAYS = (7, 14, 30, 60)


@dataclass(frozen=True)
class ReviewHistoryItem:
    """The scheduling facts for one earlier review, newest first."""

    result_score: float
    assisted: bool
    schedule_applied: bool


def independent_success_streak(prior_reviews: Sequence[ReviewHistoryItem]) -> int:
    """Count consecutive independent successes that actually shifted schedule."""
    streak = 0
    for review in prior_reviews:
        if (
            not isinstance(review, ReviewHistoryItem)
            or not isinstance(review.result_score, (int, float))
            or isinstance(review.result_score, bool)
            or not isfinite(review.result_score)
            or not 0 <= review.result_score <= 1
            or type(review.assisted) is not bool
            or type(review.schedule_applied) is not bool
        ):
            raise InvalidEvidence("Review history is invalid")
        if not review.schedule_applied:
            continue
        if review.result_score < 1.0 or review.assisted:
            break
        streak += 1
    return streak


def review_interval_days(
    *,
    result_score: float,
    assisted: bool,
    prior_reviews: Sequence[ReviewHistoryItem] = (),
) -> int:
    """Return a simple scheduling interval, not a prediction of retention.

    Only schedule-applied reviews contribute to the independent-success
    streak. Unapplied same-day observations are ignored; an applied failure or
    assisted success breaks that streak.
    """
    if (
        not isinstance(result_score, (int, float))
        or isinstance(result_score, bool)
        or not isfinite(result_score)
        or not 0 <= result_score <= 1
    ):
        raise InvalidEvidence("Review score is invalid")
    if type(assisted) is not bool:
        raise InvalidEvidence("Review assistance is invalid")

    independent_streak = independent_success_streak(prior_reviews)

    if result_score < 1.0:
        return 1
    if assisted:
        return 3
    return _REVIEW_INTERVALS_DAYS[
        min(independent_streak, len(_REVIEW_INTERVALS_DAYS) - 1)
    ]


def record_review_attempt(
    db: Session,
    *,
    user_id: UUID,
    review_session_id: UUID,
    result_score: float,
    idempotency_key: str,
    answers: dict[str, str] | None = None,
) -> ReviewAttempt:
    """Append a server-graded delayed-review result and its retention evidence.

    The caller must supply the authenticated user and a score already graded
    against the session's immutable ExerciseVersion snapshot. This function
    derives hint attribution and owns no commit; evidence, attempt, projection,
    and session consumption must be committed or rolled back together.
    """
    if (
        not isinstance(result_score, (int, float))
        or isinstance(result_score, bool)
        or not isfinite(result_score)
        or not 0 <= result_score <= 1
    ):
        raise InvalidEvidence("Review score is invalid")
    if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 240:
        raise InvalidEvidence("Review idempotency key is invalid")
    if answers is not None:
        if (
            not isinstance(answers, dict)
            or not 1 <= len(answers) <= 20
            or not all(isinstance(key, str) and 1 <= len(key) <= 100 for key in answers)
            or not all(isinstance(value, str) and 1 <= len(value) <= 200 for value in answers.values())
        ):
            raise InvalidEvidence("Review answers are invalid")

    try:
        user_id = UUID(str(user_id))
        review_session_id = UUID(str(review_session_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidEvidence("Review owner or session ID is invalid") from exc

    event_at = datetime.now(timezone.utc)
    request_key = "sha256:" + sha256(idempotency_key.encode("utf-8")).hexdigest()

    # Serialize per-user review submissions before checking replay/due state.
    if db.scalar(select(User.id).where(User.id == user_id).with_for_update()) is None:
        raise InvalidEvidence("Review owner does not exist")

    existing = db.scalar(
        select(ReviewAttempt).where(
            ReviewAttempt.user_id == user_id,
            ReviewAttempt.idempotency_key == request_key,
        )
    )
    if existing is not None:
        evidence = db.get(SkillEvidence, existing.skill_evidence_id)
        if (
            existing.review_session_id != review_session_id
            or evidence is None
            or evidence.source_type != "review_attempt"
            or not evidence.retention_only
            or evidence.result_score != float(result_score)
            or existing.answers != answers
        ):
            raise InvalidEvidence("Review idempotency key was reused with different input")
        return existing

    session = db.get(ReviewSession, review_session_id)
    if (
        session is None
        or session.user_id != user_id
        or session.completed_at is not None
    ):
        raise InvalidEvidence("Review session is unavailable")

    # Assistance is never accepted from the caller; count distinct reveals on
    # this exact immutable exercise version that existed by the response time.
    assisted, hint_count = derive_review_assistance(
        db,
        user_id=user_id,
        review_session_id=review_session_id,
        occurred_at=event_at,
    )
    attempt_id = uuid4()
    evidence = _record_review_evidence(
        db,
        user_id=user_id,
        review_session_id=session.id,
        source_id=attempt_id,
        result_score=float(result_score),
        assisted=assisted,
        hint_count=hint_count,
        occurred_at=event_at,
        metadata={"review_request_key_hash": request_key},
    )
    review_meta = evidence.evidence_metadata.get("review_policy", {})
    attempt = ReviewAttempt(
        id=attempt_id,
        review_session_id=session.id,
        user_id=user_id,
        skill_id=session.skill_id,
        exercise_version_id=session.exercise_version_id,
        skill_evidence_id=evidence.id,
        evidence_source_type="review_attempt",
        scheduled_for=session.scheduled_for,
        applied_on=event_at.date() if review_meta.get("schedule_applied") else None,
        idempotency_key=request_key,
        answers=answers,
        occurred_at=event_at,
    )
    db.add(attempt)
    session.completed_at = event_at
    db.flush()
    return attempt
