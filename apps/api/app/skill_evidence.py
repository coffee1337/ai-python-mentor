"""Transactional, append-only skill evidence and UserSkill projection."""
from datetime import datetime, timedelta, timezone
from math import isfinite
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AssessmentResponse,
    AssessmentRun,
    CodingAttempt,
    ExerciseVersion,
    HintReveal,
    KnowledgeCheckAttempt,
    SubmissionResult,
    User,
)
from app.db.models import ReviewAttempt, ReviewSession, Skill, SkillEvidence, SkillMasteryAudit, UserSkill
from app.exercise_snapshots import snapshot_assessment, snapshot_checks, snapshot_skill_id
from app.runner import MAX_TESTS, PROTOCOL_VERSION
from app.skill_graph import seed_skill_graph


class InvalidEvidence(ValueError):
    pass


def _valid_score(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and 0 <= value <= 1
    )


def _mastery(skill: UserSkill) -> float:
    return max(0.0, min(1.0, 0.45 * skill.independent_score + 0.35 * skill.knowledge_score + 0.20 * skill.practice_score))


def _as_utc(value: datetime) -> datetime:
    """Normalize database timestamps (including SQLite's naive values) to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def review_interval_days(
    *, result_score: float, assisted: bool, independent_streak: int
) -> int:
    """Backward-compatible adapter for callers using the old pure policy API."""
    from app.reviews import ReviewHistoryItem, review_interval_days as _review_interval_days

    if (
        not isinstance(independent_streak, int)
        or isinstance(independent_streak, bool)
        or independent_streak < 0
    ):
        raise InvalidEvidence("Review history is invalid")
    return _review_interval_days(
        result_score=result_score,
        assisted=assisted,
        prior_reviews=[
            ReviewHistoryItem(result_score=1.0, assisted=False, schedule_applied=True)
            for _ in range(independent_streak)
        ],
    )


def _exercise_version_id_for_source(
    db: Session, *, source_type: str, source_id: str
) -> UUID | None:
    if source_type == "assessment_response":
        response = db.get(AssessmentResponse, UUID(source_id))
        return response.exercise_version_id if response is not None else None
    if source_type == "knowledge_check_attempt":
        attempt = db.get(KnowledgeCheckAttempt, UUID(source_id))
        return attempt.exercise_version_id if attempt is not None else None
    if source_type == "review_attempt":
        attempt = db.get(ReviewAttempt, UUID(source_id))
        return attempt.exercise_version_id if attempt is not None else None
    return None


def _source_timestamp(db: Session, *, source_type: str, source_id: str) -> datetime | None:
    if source_type == "assessment_response":
        source = db.get(AssessmentResponse, UUID(source_id))
    elif source_type == "knowledge_check_attempt":
        source = db.get(KnowledgeCheckAttempt, UUID(source_id))
    elif source_type == "review_attempt":
        source = db.get(ReviewAttempt, UUID(source_id))
    else:
        return None
    if source is None:
        return None
    return source.occurred_at if source_type == "review_attempt" else source.created_at


def _coding_evidence_context(
    db: Session, *, user_id: UUID, source_id: str
) -> tuple[CodingAttempt, SubmissionResult, str, float]:
    """Load and validate the server-owned, version-bound coding result."""
    try:
        canonical_source_id = str(UUID(source_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidEvidence("Invalid coding attempt ID") from exc

    attempt = db.get(CodingAttempt, UUID(canonical_source_id))
    if attempt is None or attempt.user_id != user_id:
        raise InvalidEvidence("Coding evidence is not owned by this user")
    if attempt.language != "python" or attempt.mode != "function":
        raise InvalidEvidence("Coding attempt is outside the trusted runner allowlist")
    if attempt.exercise_version_id is None:
        raise InvalidEvidence("Coding attempt has no trusted exercise version")

    version = db.get(ExerciseVersion, attempt.exercise_version_id)
    if version is None or version.exercise_id != attempt.exercise_id:
        raise InvalidEvidence("Coding attempt exercise version is invalid")
    try:
        skill_id = snapshot_skill_id(
            version.content_snapshot,
            exercise_id=attempt.exercise_id,
            version=version.version,
        )
    except ValueError as exc:
        raise InvalidEvidence("Coding attempt snapshot has no trusted skill mapping") from exc

    result = db.scalar(
        select(SubmissionResult).where(
            SubmissionResult.coding_attempt_id == attempt.id,
        )
    )
    if result is None:
        raise InvalidEvidence("Coding attempt has no normalized runner result")
    if (
        result.exercise_version_id != attempt.exercise_version_id
        or result.idempotency_key != str(attempt.id)
        or result.protocol_version != PROTOCOL_VERSION
        or result.status not in {"passed", "failed"}
        or attempt.status != result.status
        or type(result.tests_passed) is not int
        or type(result.tests_total) is not int
        or result.tests_total <= 0
        or result.tests_total > MAX_TESTS
        or result.tests_passed < 0
        or result.tests_passed > MAX_TESTS
        or result.tests_passed > result.tests_total
        or result.timeout
        or result.resource_violation
        or result.created_at is None
    ):
        raise InvalidEvidence("Coding runner result is not trustworthy")
    if result.status == "passed" and result.tests_passed != result.tests_total:
        raise InvalidEvidence("Passed coding result has incomplete test counts")
    if result.status == "failed" and result.tests_passed == result.tests_total:
        raise InvalidEvidence("Failed coding result has complete test counts")
    snapshot = version.content_snapshot
    if isinstance(snapshot, dict) and snapshot.get("kind") == "authored_python_function":
        cases = snapshot.get("coding", {}).get("cases", [])
        if result.tests_total != len(cases):
            raise InvalidEvidence("Coding runner result does not cover the bound authored test contract")

    return (
        attempt,
        result,
        skill_id,
        result.tests_passed / result.tests_total,
    )


def _derive_assistance_for_version(
    db: Session, *, user_id: UUID, exercise_version_id: UUID, occurred_at: datetime
) -> tuple[bool, int]:
    levels = db.scalars(
        select(HintReveal.level).where(
            HintReveal.user_id == user_id,
            HintReveal.exercise_version_id == exercise_version_id,
            HintReveal.revealed_at <= occurred_at,
        ).distinct()
    ).all()
    hint_count = len(levels)
    if not 0 <= hint_count <= 5:
        raise InvalidEvidence("Evidence hint count is invalid")
    return hint_count > 0, hint_count


def derive_assistance(
    db: Session, *, user_id: UUID, source_type: str, source_id: str
) -> tuple[bool, int]:
    """Derive assistance from the exact exercise version recorded by the source."""
    if source_type == "coding_attempt":
        attempt, result, _, _ = _coding_evidence_context(
            db,
            user_id=user_id,
            source_id=source_id,
        )
        return _derive_assistance_for_version(
            db,
            user_id=user_id,
            exercise_version_id=attempt.exercise_version_id,
            occurred_at=_as_utc(result.created_at),
        )
    source_version_id = _exercise_version_id_for_source(
        db, source_type=source_type, source_id=source_id
    )
    if source_version_id is None:
        raise InvalidEvidence("Evidence source has no trusted exercise version")
    source_timestamp = _source_timestamp(db, source_type=source_type, source_id=source_id)
    if source_timestamp is None:
        raise InvalidEvidence("Evidence source has no timestamp")
    return _derive_assistance_for_version(
        db,
        user_id=user_id,
        exercise_version_id=source_version_id,
        occurred_at=_as_utc(source_timestamp),
    )


def derive_review_assistance(
    db: Session, *, user_id: UUID, review_session_id: UUID, occurred_at: datetime
) -> tuple[bool, int]:
    """Derive review hints from the session's exact version as of completion."""
    session = db.get(ReviewSession, review_session_id)
    if session is None or session.user_id != user_id:
        raise InvalidEvidence("Review session is not owned by this user")
    return _derive_assistance_for_version(
        db,
        user_id=user_id,
        exercise_version_id=session.exercise_version_id,
        occurred_at=_as_utc(occurred_at),
    )


def _assisted_independent_score(current: float, result_score: float, hint_count: int) -> float:
    """Hints reduce independent credit by 20% per revealed level; level 5 gives zero."""
    factor = max(0.0, 1.0 - 0.20 * hint_count)
    return min(current, result_score) * factor


def _record_evidence(
    db: Session,
    *,
    user_id: UUID,
    skill_id: str | None,
    source_type: str,
    source_id: str,
    result_score: float | None,
    assisted: bool = False,
    hint_count: int = 0,
    occurred_at: datetime | None = None,
    metadata: dict | None = None,
    review_session_id: UUID | None = None,
    _allow_pending_review_attempt: bool = False,
) -> SkillEvidence:
    """Record one objective signal. Caller owns the surrounding transaction."""
    coding_context: tuple[CodingAttempt, SubmissionResult, str, float] | None = None
    if source_type == "coding_attempt":
        coding_context = _coding_evidence_context(
            db,
            user_id=user_id,
            source_id=source_id,
        )
        _, coding_result, snapshot_skill, snapshot_score = coding_context
        if skill_id is not None and skill_id != snapshot_skill:
            raise InvalidEvidence("Coding evidence skill must come from its snapshot")
        if result_score is not None and result_score != snapshot_score:
            raise InvalidEvidence("Coding evidence score must come from test counts")
        if occurred_at is not None and _as_utc(occurred_at) != _as_utc(coding_result.created_at):
            raise InvalidEvidence("Coding evidence timestamp must come from runner result")
        skill_id = snapshot_skill
        result_score = snapshot_score
        event_at = _as_utc(coding_result.created_at)
    else:
        event_at = _as_utc(occurred_at or datetime.now(timezone.utc))
    if skill_id is None or result_score is None:
        raise InvalidEvidence("Evidence skill and score are required")
    # Serialize evidence projection updates per owner on databases supporting row locks.
    if db.scalar(select(User.id).where(User.id == user_id).with_for_update()) is None:
        raise InvalidEvidence("Evidence owner does not exist")
    seed_skill_graph(db)
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise InvalidEvidence(f"Unknown skill: {skill_id}")
    if source_type not in {
        "assessment_response", "knowledge_check_attempt", "coding_attempt", "review_attempt"
    }:
        raise InvalidEvidence(f"Unsupported source type: {source_type}")
    if (
        not _valid_score(result_score)
        or type(assisted) is not bool
        or isinstance(hint_count, bool)
        or not isinstance(hint_count, int)
        or not 0 <= hint_count <= 5
    ):
        raise InvalidEvidence("Evidence score or hint count is invalid")
    review_session: ReviewSession | None = None
    review_version: ExerciseVersion | None = None
    canonical_source_id: str | None = None
    if source_type == "assessment_response":
        try:
            canonical_source_id = str(UUID(source_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise InvalidEvidence("Invalid assessment response ID") from exc
        response = db.get(AssessmentResponse, UUID(canonical_source_id))
        run = db.get(AssessmentRun, response.run_id) if response is not None else None
        if response is None or run is None or run.user_id != user_id or run.status != "completed" or response.skill_id != skill_id:
            raise InvalidEvidence("Assessment evidence is not owned or does not match a completed run")
        if response.exercise_version_id is None:
            raise InvalidEvidence("Assessment response has no trusted exercise version")
        version = db.get(ExerciseVersion, response.exercise_version_id)
        snapshot = version.content_snapshot if version is not None else None
        question = snapshot_assessment(snapshot) if isinstance(snapshot, dict) else None
        if (
            question is None
            or version.exercise_id != response.question_id
            or question.get("id") != response.question_id
            or question.get("skill_id") != skill_id
            or question.get("difficulty") != response.difficulty
            or not isinstance(question.get("choices"), list)
            or response.answer not in question["choices"]
            or not isinstance(question.get("answer"), str)
            or response.is_correct != (response.answer == question["answer"])
            or result_score != float(response.is_correct)
        ):
            raise InvalidEvidence("Assessment evidence does not match authored question")
    elif source_type == "knowledge_check_attempt":
        try:
            canonical_source_id = str(UUID(source_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise InvalidEvidence("Invalid knowledge-check attempt ID") from exc
        attempt = db.get(KnowledgeCheckAttempt, UUID(canonical_source_id))
        if attempt is None or attempt.user_id != user_id or attempt.skill_id != skill_id or attempt.score != result_score:
            raise InvalidEvidence("Knowledge-check evidence is not owned or does not match attempt")
        if attempt.exercise_version_id is None:
            raise InvalidEvidence("Knowledge-check attempt has no trusted exercise version")
        version = db.get(ExerciseVersion, attempt.exercise_version_id)
        snapshot = version.content_snapshot if version is not None else None
        lesson = snapshot.get("lesson") if isinstance(snapshot, dict) else None
        questions = snapshot_checks(snapshot) if isinstance(snapshot, dict) else ()
        if (
            version is None
            or version.exercise_id != attempt.lesson_id
            or not isinstance(lesson, dict)
            or lesson.get("id") != attempt.lesson_id
            or lesson.get("skill_id") != skill_id
            or not questions
        ):
            raise InvalidEvidence("Knowledge-check evidence does not match content snapshot")
    elif source_type == "review_attempt":
        try:
            canonical_source_id = str(UUID(source_id))
            if review_session_id is not None:
                review_session_id = UUID(str(review_session_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise InvalidEvidence("Invalid review evidence source") from exc
        source_attempt = db.get(ReviewAttempt, UUID(canonical_source_id))
        if source_attempt is not None:
            # Replays may validate against the already-persisted immutable source.
            review_session_id = source_attempt.review_session_id
            if (
                source_attempt.user_id != user_id
                or source_attempt.skill_id != skill_id
                or source_attempt.evidence_source_type != "review_attempt"
                or source_attempt.occurred_at is None
                or _as_utc(source_attempt.occurred_at) != event_at
            ):
                raise InvalidEvidence("Review evidence does not match its persisted attempt")
        if review_session_id is None:
            raise InvalidEvidence("Review evidence requires a server-owned review session")
        if source_attempt is None and not _allow_pending_review_attempt:
            raise InvalidEvidence("Review evidence must be recorded through the review service")
        review_session = db.get(ReviewSession, review_session_id)
        if (
            review_session is None
            or review_session.user_id != user_id
            or review_session.skill_id != skill_id
        ):
            raise InvalidEvidence("Review session is not owned by this user or skill")
        if source_attempt is None and review_session.completed_at is not None:
            raise InvalidEvidence("Review session has already been completed")
        if review_session.exercise_version_id is None:
            raise InvalidEvidence("Review session has no trusted exercise version")
        review_version = db.get(ExerciseVersion, review_session.exercise_version_id)
        snapshot = review_version.content_snapshot if review_version is not None else None
        lesson = snapshot.get("lesson") if isinstance(snapshot, dict) else None
        assessment = snapshot_assessment(snapshot) if isinstance(snapshot, dict) else None
        snapshot_skill_id = (
            lesson.get("skill_id") if isinstance(lesson, dict)
            else assessment.get("skill_id") if isinstance(assessment, dict)
            else None
        )
        if (
            review_version is None
            or not isinstance(snapshot, dict)
            or snapshot.get("exercise_id") != review_version.exercise_id
            or snapshot_skill_id != skill_id
            or review_session.scheduled_for > event_at.date()
        ):
            raise InvalidEvidence("Review evidence does not match the bound exercise snapshot")
    else:
        assert coding_context is not None
        canonical_source_id = str(coding_context[0].id)
        source_id = canonical_source_id
    if source_type in {"assessment_response", "knowledge_check_attempt", "review_attempt"}:
        source_id = canonical_source_id
    if source_type == "coding_attempt":
        assert coding_context is not None
        expected_assisted, expected_hint_count = _derive_assistance_for_version(
            db,
            user_id=user_id,
            exercise_version_id=coding_context[0].exercise_version_id,
            occurred_at=event_at,
        )
    elif source_type == "review_attempt":
        assert review_version is not None
        expected_assisted, expected_hint_count = _derive_assistance_for_version(
            db,
            user_id=user_id,
            exercise_version_id=review_version.id,
            occurred_at=event_at,
        )
    else:
        expected_assisted, expected_hint_count = derive_assistance(
            db, user_id=user_id, source_type=source_type, source_id=source_id
        )
    if source_type == "coding_attempt":
        # Assistance is derived from the server-side reveal ledger; callers,
        # including the worker, cannot choose these fields.
        assisted, hint_count = expected_assisted, expected_hint_count
    elif assisted != expected_assisted or hint_count != expected_hint_count:
        raise InvalidEvidence("Evidence assistance does not match recorded hint usage")
    key = f"v1:{source_type}:{source_id}:{skill_id}"
    existing = db.scalar(select(SkillEvidence).where(SkillEvidence.user_id == user_id, SkillEvidence.idempotency_key == key))
    if existing is not None:
        if (
            existing.source_type != source_type
            or existing.source_id != source_id
            or existing.skill_id != skill_id
            or existing.result_score != result_score
            or existing.assisted != assisted
            or existing.hint_count != hint_count
        ):
            raise InvalidEvidence("Idempotency key was reused with different evidence")
        return existing

    # Re-check after the owner lock: another transaction may have committed
    # this source while the first lookup was running.
    existing = db.scalar(select(SkillEvidence).where(SkillEvidence.user_id == user_id, SkillEvidence.idempotency_key == key))
    if existing is not None:
        if existing.assisted != assisted or existing.hint_count != hint_count:
            raise InvalidEvidence("Idempotency key was reused with different evidence")
        return existing

    mastery = db.scalar(select(UserSkill).where(UserSkill.user_id == user_id, UserSkill.skill_id == skill_id).with_for_update())
    if mastery is None:
        if source_type == "review_attempt":
            raise InvalidEvidence("Review requires an existing due skill schedule")
        mastery = UserSkill(user_id=user_id, skill_id=skill_id)
        db.add(mastery)
        db.flush()
    db.execute(select(UserSkill.id).where(UserSkill.id == mastery.id).with_for_update()).scalar_one()
    before = _mastery(mastery)
    count = mastery.evidence_count
    evidence_metadata = dict(metadata or {})
    if source_type == "review_attempt":
        assert review_session is not None
        review_day = event_at.date()
        already_applied = db.scalar(
            select(ReviewAttempt.id).where(
                ReviewAttempt.user_id == user_id,
                ReviewAttempt.skill_id == skill_id,
                ReviewAttempt.applied_on == review_day,
            ).limit(1)
        ) is not None
        if (
            mastery.next_review_at is None
            or _as_utc(mastery.next_review_at) > event_at
        ) and not already_applied:
            raise InvalidEvidence("Review is not due yet")
        prior_reviews = db.execute(
            select(ReviewAttempt, SkillEvidence)
            .join(SkillEvidence, SkillEvidence.id == ReviewAttempt.skill_evidence_id)
            .where(
                ReviewAttempt.user_id == user_id,
                ReviewAttempt.skill_id == skill_id,
                ReviewAttempt.applied_on.is_not(None),
            )
            .order_by(ReviewAttempt.occurred_at.desc(), ReviewAttempt.id.desc())
        ).all()
        from app.reviews import (
            REVIEW_POLICY_VERSION,
            ReviewHistoryItem,
            independent_success_streak,
            review_interval_days,
        )

        prior_review_history = [
            ReviewHistoryItem(
                result_score=float(prior_evidence.result_score),
                assisted=bool(prior_evidence.assisted),
                schedule_applied=prior_attempt.applied_on is not None,
            )
            for prior_attempt, prior_evidence in prior_reviews
        ]
        correct = result_score >= 1.0
        due_before = _as_utc(mastery.next_review_at) if mastery.next_review_at is not None else None
        interval_days = review_interval_days(
            result_score=result_score,
            assisted=assisted,
            prior_reviews=prior_review_history,
        )
        schedule_applied = not already_applied
        due_after = (
            event_at + timedelta(days=interval_days)
            if schedule_applied
            else due_before
        )
        evidence_metadata["review_policy"] = {
            "version": REVIEW_POLICY_VERSION,
            "interval_days": interval_days if schedule_applied else None,
            "schedule_applied": schedule_applied,
            "utc_review_day": review_day.isoformat(),
            "prior_independent_streak": independent_success_streak(
                prior_review_history
            ),
            "due_before": due_before.isoformat() if due_before is not None else None,
            "due_after": due_after.isoformat() if due_after is not None else None,
            "outcome": "incorrect" if not correct else "supported" if assisted else "independent",
        }

        # Retention is a separate signal. Do not award acquisition/mastery credit,
        # or increment evidence_count (used by the existing knowledge-check policy).
        mastery.retention_score = result_score
        if mastery.last_practiced_at is None or _as_utc(mastery.last_practiced_at) < event_at:
            mastery.last_practiced_at = event_at
        if schedule_applied:
            mastery.next_review_at = due_after
    else:
        weight = 0.35 if assisted else 1.0
        effective = result_score * weight
        prior_knowledge_weight = mastery.mastery_weight
        new_knowledge_weight = prior_knowledge_weight + weight
        mastery.knowledge_score = ((mastery.knowledge_score * prior_knowledge_weight) + effective) / new_knowledge_weight
        mastery.mastery_weight = new_knowledge_weight
        mastery.independent_score = (
            max(mastery.independent_score, result_score)
            if not assisted
            else _assisted_independent_score(mastery.independent_score, result_score, hint_count)
        )
        mastery.practice_score = max(mastery.practice_score, effective)
        mastery.retention_score = result_score
        mastery.evidence_count = count + 1
        mastery.confidence = min(1.0, new_knowledge_weight / 5)
        mastery.last_practiced_at = event_at
    evidence = SkillEvidence(
        user_id=user_id, skill_id=skill_id, source_type=source_type, source_id=source_id,
        retention_only=source_type == "review_attempt",
        result_score=result_score, assisted=assisted, hint_count=hint_count,
        occurred_at=event_at, idempotency_key=key,
        evidence_metadata=evidence_metadata,
    )
    db.add(evidence)
    db.flush()
    db.add(SkillMasteryAudit(
        evidence_id=evidence.id, user_id=user_id, skill_id=skill_id,
        before_mastery=before, after_mastery=_mastery(mastery),
        before_evidence_count=count, after_evidence_count=mastery.evidence_count,
        policy_version=(
            evidence_metadata.get("review_policy", {}).get("version", "v1")
            if source_type == "review_attempt"
            else "v1"
        ),
    ))
    return evidence


def record_evidence(
    db: Session,
    *,
    user_id: UUID,
    skill_id: str | None = None,
    source_type: str,
    source_id: str,
    result_score: float | None = None,
    assisted: bool = False,
    hint_count: int = 0,
    occurred_at: datetime | None = None,
    metadata: dict | None = None,
) -> SkillEvidence:
    """Record server-validated evidence; review uses the review service.

    Coding evidence derives skill, score, timestamp and assistance from the
    persisted version snapshot, normalized result and reveal ledger.
    """
    if source_type == "review_attempt":
        raise InvalidEvidence("Review evidence must be recorded through the review service")
    evidence = _record_evidence(
        db,
        user_id=user_id,
        skill_id=skill_id,
        source_type=source_type,
        source_id=source_id,
        result_score=result_score,
        assisted=assisted,
        hint_count=hint_count,
        occurred_at=occurred_at,
        metadata=metadata,
    )
    if source_type == "coding_attempt":
        attempt, result, _, _ = _coding_evidence_context(
            db,
            user_id=user_id,
            source_id=source_id,
        )
        if result.skill_evidence_id not in {None, evidence.id}:
            raise InvalidEvidence("Coding result is already linked to different evidence")
        result.skill_evidence_id = evidence.id
        db.flush()
    return evidence


def _record_review_evidence(
    db: Session,
    *,
    user_id: UUID,
    review_session_id: UUID,
    source_id: UUID,
    result_score: float,
    assisted: bool,
    hint_count: int,
    occurred_at: datetime,
    metadata: dict,
) -> SkillEvidence:
    """Internal insertion order for the review-attempt/evidence FK cycle."""
    session = db.get(ReviewSession, review_session_id)
    if session is None:
        raise InvalidEvidence("Review session does not exist")
    return _record_evidence(
        db,
        user_id=user_id,
        skill_id=session.skill_id,
        source_type="review_attempt",
        source_id=str(source_id),
        result_score=result_score,
        assisted=assisted,
        hint_count=hint_count,
        occurred_at=occurred_at,
        metadata=metadata,
        review_session_id=review_session_id,
        _allow_pending_review_attempt=True,
    )
