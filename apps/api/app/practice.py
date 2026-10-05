"""Owned coding-attempt API. Runner is fail-closed and never executes locally."""
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import csrf_protected, current_auth
from app.db.models import AuthSession, CodingAttempt, SubmissionResult, User
from app.db.session import get_db
from app.learning import (
    _lesson_session_version,
    _pending_lesson_session,
    _persisted_lesson_version,
    accessible_lesson,
    require_onboarding,
)
from app.runner import MAX_TESTS, PROTOCOL_VERSION, RunnerError, RunnerResult, RunnerUnavailable, runner
from app.skill_evidence import InvalidEvidence, record_evidence

router = APIRouter(prefix="/learning", tags=["practice"])
_RATE: dict[str, list[float]] = {}
_LOCK = Lock()
LIMIT = 5
WINDOW = 60.0
MAX_CODE = 20000

class AttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str = Field(min_length=1, max_length=20)
    mode: str = Field(min_length=1, max_length=20)
    source_code: str = Field(min_length=1, max_length=MAX_CODE)

class AttemptResponse(BaseModel):
    id: UUID
    exercise_id: str
    language: str
    mode: str
    status: str
    result: dict
    created_at: datetime

def _rate_limit(user_id: UUID) -> None:
    now = monotonic(); key = str(user_id)
    with _LOCK:
        recent = [stamp for stamp in _RATE.get(key, []) if now - stamp < WINDOW]
        if len(recent) >= LIMIT:
            raise HTTPException(429, "Too many submissions; try again later")
        _RATE[key] = recent + [now]

def _response(row: CodingAttempt) -> AttemptResponse:
    return AttemptResponse(id=row.id, exercise_id=row.exercise_id, language=row.language, mode=row.mode, status=row.status, result=json.loads(row.result or "{}"), created_at=row.created_at)


def _persist_submission_result(
    db: Session, attempt: CodingAttempt, result: RunnerResult
) -> SubmissionResult:
    """Persist the bounded normalized result for this exact attempt/version."""
    if attempt.exercise_version_id is None:
        raise RunnerError("Submission result requires a pinned exercise version")
    if (
        type(result.tests_passed) is not int
        or type(result.tests_total) is not int
        or result.tests_passed < 0
        or result.tests_total < 0
        or result.tests_passed > MAX_TESTS
        or result.tests_total > MAX_TESTS
        or result.tests_passed > result.tests_total
        or type(result.timeout) is not bool
        or type(result.resource_violation) is not bool
        or result.status not in {
            "passed",
            "failed",
            "timeout",
            "resource_violation",
            "error",
            "runner_error",
            "unavailable",
        }
    ):
        raise RunnerError("Runner result counts or flags are invalid")
    if result.status in {"passed", "failed"} and (
        result.tests_total == 0
        or result.timeout
        or result.resource_violation
        or (result.status == "passed") != (result.tests_passed == result.tests_total)
    ):
        raise RunnerError("Runner terminal result is inconsistent")
    if result.status == "timeout" and (
        not result.timeout or result.resource_violation
    ):
        raise RunnerError("Runner timeout result is inconsistent")
    if result.status == "resource_violation" and (
        not result.resource_violation or result.timeout
    ):
        raise RunnerError("Runner resource result is inconsistent")
    if result.status in {"error", "runner_error", "unavailable"} and (
        result.timeout or result.resource_violation
    ):
        raise RunnerError("Runner failure result is inconsistent")
    existing = db.scalar(
        select(SubmissionResult).where(
            SubmissionResult.coding_attempt_id == attempt.id,
        )
    )
    if existing is not None:
        if (
            existing.exercise_version_id != attempt.exercise_version_id
            or existing.idempotency_key != str(attempt.id)
            or existing.status != result.status
            or existing.tests_passed != result.tests_passed
            or existing.tests_total != result.tests_total
            or existing.timeout != result.timeout
            or existing.resource_violation != result.resource_violation
        ):
            raise RunnerError("Coding attempt result was reused with different data")
        return existing
    row = SubmissionResult(
        coding_attempt_id=attempt.id,
        exercise_version_id=attempt.exercise_version_id,
        idempotency_key=str(attempt.id),
        protocol_version=PROTOCOL_VERSION,
        status=result.status,
        tests_passed=result.tests_passed,
        tests_total=result.tests_total,
        timeout=result.timeout,
        resource_violation=result.resource_violation,
        exit_code=result.exit_code,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def _persist_result_and_evidence(
    db: Session, attempt: CodingAttempt, result: RunnerResult
) -> None:
    """Commit a result and its evidence atomically when the evidence is valid.

    A malformed snapshot or other proven-invalid evidence condition never
    creates partial evidence; the normalized result remains available without
    mastery credit.
    """
    attempt.status = result.status
    attempt.result = json.dumps(result.__dict__)
    try:
        with db.begin_nested():
            submission = _persist_submission_result(db, attempt, result)
            if result.status in {"passed", "failed"}:
                evidence = record_evidence(
                    db,
                    user_id=attempt.user_id,
                    skill_id=None,
                    source_type="coding_attempt",
                    source_id=str(attempt.id),
                    result_score=None,
                    metadata={"protocol_version": PROTOCOL_VERSION},
                )
                submission.skill_evidence_id = evidence.id
    except InvalidEvidence:
        # Keep the objective result, but do not award unverifiable learning
        # credit. The savepoint removes any partial evidence/projection writes.
        _persist_submission_result(db, attempt, result)
    except RunnerError:
        # A result object that fails the persistence-side contract is itself
        # untrustworthy. Preserve only a bounded failure tombstone.
        result = RunnerResult(
            status="runner_error",
            message="Runner failed",
            tests_passed=0,
            tests_total=0,
            timeout=False,
            resource_violation=False,
        )
        attempt.status = result.status
        attempt.result = json.dumps(result.__dict__)
        with db.begin_nested():
            _persist_submission_result(db, attempt, result)
    db.commit()


def _unavailable_result(message: str) -> RunnerResult:
    return RunnerResult(
        status="unavailable",
        message=message,
        tests_passed=0,
        tests_total=0,
        timeout=False,
        resource_violation=False,
    )


@router.get("/exercises/{exercise_id}/attempts", response_model=list[AttemptResponse])
def history(exercise_id: str, auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    require_onboarding(auth[0]); accessible_lesson(exercise_id, db, auth[0])
    rows = db.scalars(select(CodingAttempt).where(CodingAttempt.user_id == auth[0].id, CodingAttempt.exercise_id == exercise_id).order_by(CodingAttempt.created_at.desc()).limit(20)).all()
    return [_response(row) for row in rows]

@router.post("/exercises/{exercise_id}/attempts", response_model=AttemptResponse, status_code=201)
def submit(exercise_id: str, payload: AttemptRequest, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    user, _ = auth; require_onboarding(user); accessible_lesson(exercise_id, db, user)
    if payload.language != "python" or payload.mode != "function":
        raise HTTPException(422, "Only Python function exercises are supported")
    _rate_limit(user.id)
    pending_session = _pending_lesson_session(db, user.id, exercise_id)
    exercise_version = (
        _lesson_session_version(db, pending_session, exercise_id)
        if pending_session is not None
        else _persisted_lesson_version(exercise_id, db)
    )
    row = CodingAttempt(
        user_id=user.id,
        exercise_id=exercise_id,
        exercise_version_id=exercise_version.id,
        language="python",
        mode="function",
        source_code=payload.source_code,
        status="unavailable",
        result=json.dumps(
            {
                "status": "unavailable",
                "message": "Изолированный runner не настроен. Код сохранён, но не выполнялся.",
                "tests_passed": 0,
                "tests_total": 0,
                "timeout": False,
                "resource_violation": False,
            }
        ),
    )
    db.add(row); db.commit(); db.refresh(row)
    # No API-process execution. If a safe adapter is installed in the future, it must be isolated.
    try:
        with runner.attempt_context(exercise_version=exercise_version.version, idempotency_key=str(row.id)):
            result = runner.run(
                exercise_id=exercise_id,
                source_code=payload.source_code,
                language="python",
                mode="function",
            )
    except TimeoutError:
        normalized = RunnerResult(
            status="timeout",
            message="Runner timed out",
            tests_passed=0,
            tests_total=0,
            timeout=True,
        )
        _persist_result_and_evidence(db, row, normalized)
        db.refresh(row)
    except (RunnerUnavailable, RunnerError):
        normalized = _unavailable_result(
            "Изолированный runner недоступен. Код сохранён, но не выполнялся."
        )
        _persist_result_and_evidence(db, row, normalized)
        db.refresh(row)
    except Exception:
        normalized = RunnerResult(
            status="runner_error",
            message="Runner failed",
            tests_passed=0,
            tests_total=0,
            timeout=False,
            resource_violation=False,
        )
        _persist_result_and_evidence(db, row, normalized)
        db.refresh(row)
    else:
        _persist_result_and_evidence(db, row, result)
        db.refresh(row)
    return _response(row)
