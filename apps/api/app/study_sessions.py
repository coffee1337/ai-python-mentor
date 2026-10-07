"""Durable, owned study time with bounded presence leases.

These records describe an explicitly started timer, never course mastery or
completion. A GET can project an expired timer as paused but cannot renew it.
"""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.account_services import throttle
from app.auth import account_scoped_auth, account_scoped_csrf
from app.db.models import AuthSession, User
from app.db.session import get_db
from app.db.study_session_models import StudySession
from app.learning import require_onboarding
from app.study_progress import FOCUS_LIMIT, TodayFocus, TodayResponse, today

router = APIRouter(prefix="/learning", tags=["study-sessions"])
IDLE_TIMEOUT_SECONDS = 60
MAX_ACTIVE_SECONDS = 8 * 60 * 60
OPEN_STATUSES = ("active", "paused")
StudyStatus = Literal["active", "paused", "completed", "abandoned"]
StudyAction = Literal["pause", "resume", "finish", "abandon", "heartbeat"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartRequest(StrictModel):
    pass


class RevisionRequest(StrictModel):
    expected_revision: int = Field(ge=1, le=2147483646, strict=True)


class StudySessionResponse(StrictModel):
    id: UUID
    status: StudyStatus
    revision: int
    started_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    active_seconds: int
    as_of: datetime
    focus: list[TodayFocus] = Field(max_length=FOCUS_LIMIT)
    estimated_minutes: int
    target_minutes: int
    idle_timeout_seconds: Literal[60] = IDLE_TIMEOUT_SECONDS


class CurrentStudySession(StrictModel):
    session: StudySessionResponse | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _elapsed_milliseconds(row: StudySession, now: datetime) -> int:
    if row.status != "active" or row.last_activity_at is None:
        return 0
    delta = max(0, int((_utc(now) - _utc(row.last_activity_at)).total_seconds() * 1000))
    return min(IDLE_TIMEOUT_SECONDS * 1000, delta)


def _accumulated(row: StudySession, now: datetime) -> int:
    return min(MAX_ACTIVE_SECONDS * 1000, row.accumulated_milliseconds + _elapsed_milliseconds(row, now))


def _expired(row: StudySession, now: datetime) -> bool:
    return row.status == "active" and (
        row.last_activity_at is None
        or (_utc(now) - _utc(row.last_activity_at)).total_seconds() >= IDLE_TIMEOUT_SECONDS
        or _accumulated(row, now) >= MAX_ACTIVE_SECONDS * 1000
    )


def _project(row: StudySession, now: datetime) -> StudySessionResponse:
    return StudySessionResponse(
        id=row.id, status="paused" if _expired(row, now) else row.status,
        revision=row.revision, started_at=_utc(row.started_at), updated_at=_utc(row.updated_at),
        ended_at=_utc(row.ended_at) if row.ended_at else None,
        active_seconds=_accumulated(row, now) // 1000, as_of=_utc(now),
        focus=row.focus_snapshot, estimated_minutes=row.estimated_minutes, target_minutes=row.target_minutes,
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _open_session(db: Session, user_id: UUID) -> StudySession | None:
    return db.scalar(select(StudySession).where(
        StudySession.user_id == user_id, StudySession.status.in_(OPEN_STATUSES),
    ))


@router.get("/study-session", response_model=CurrentStudySession)
def current_session(response: Response, auth: tuple[User, AuthSession] = Depends(account_scoped_auth),
                    db: Session = Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    _no_store(response)
    row = _open_session(db, user.id)
    return {"session": _project(row, _utc_now()) if row else None}


@router.get("/study-sessions", response_model=list[StudySessionResponse])
def session_history(response: Response, limit: int = Query(default=20, ge=1, le=50),
                    auth: tuple[User, AuthSession] = Depends(account_scoped_auth), db: Session = Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    _no_store(response)
    now = _utc_now()
    rows = db.scalars(select(StudySession).where(StudySession.user_id == user.id)
                      .order_by(StudySession.started_at.desc(), StudySession.id.desc()).limit(limit))
    return [_project(row, now) for row in rows]


@router.post("/study-sessions/start", response_model=StudySessionResponse)
def start_session(payload: StartRequest, response: Response,
                  auth: tuple[User, AuthSession] = Depends(account_scoped_csrf), db: Session = Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    _no_store(response)
    throttle(db, scope="study_session_user", subject=str(user.id), limit=60)
    # Serializes starts with account deletion and another start on PostgreSQL;
    # the partial unique index remains the final cross-dialect admission guard.
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    now = _utc_now()
    if current := _open_session(db, user.id):
        return _project(current, now)
    recommendation = TodayResponse.model_validate(today(auth=auth, db=db))
    if not recommendation.focus:
        raise HTTPException(409, "No study focus is available")
    row = StudySession(user_id=user.id, status="active", revision=1, started_at=now,
        updated_at=now, last_activity_at=now, accumulated_milliseconds=0,
        focus_snapshot=[item.model_dump(mode="json") for item in recommendation.focus],
        estimated_minutes=recommendation.estimated_minutes, target_minutes=recommendation.target_minutes)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        current = _open_session(db, user.id)
        if current is None:
            raise HTTPException(409, "Unable to start a study session") from None
        return _project(current, now)
    return _project(row, now)


def _transition(db: Session, user_id: UUID, session_id: UUID, action: StudyAction,
                expected_revision: int, now: datetime) -> StudySessionResponse:
    row = db.scalar(select(StudySession).where(StudySession.id == session_id,
        StudySession.user_id == user_id).with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "Study session not found")
    if row.revision != expected_revision:
        raise HTTPException(409, "Study session changed; reload before continuing")
    if row.status not in OPEN_STATUSES:
        raise HTTPException(409, "Study session has ended")
    # Keep segment boundaries monotonic if the wall clock moves backwards or
    # this request waited for a lock. It cannot recount an already closed span.
    now = max(_utc(now), _utc(row.started_at), _utc(row.updated_at),
              _utc(row.last_activity_at) if row.last_activity_at else _utc(row.updated_at))
    total = _accumulated(row, now)
    expired = _expired(row, now)
    if action == "heartbeat":
        if row.status != "active" or expired:
            raise HTTPException(409, "Study session is paused; resume explicitly")
        status = "active"
    elif action == "resume":
        if row.status != "paused" and not expired:
            raise HTTPException(409, "Study session is already active")
        if total >= MAX_ACTIVE_SECONDS * 1000:
            raise HTTPException(409, "Study session time limit reached; finish this session")
        status = "active"
    elif action == "pause":
        if row.status != "active":
            raise HTTPException(409, "Study session is already paused")
        status = "paused"
    else:
        status = "completed" if action == "finish" else "abandoned"
    # Lock plus CAS: a stale client never overwrites another tab's timer, even
    # on SQLite where SELECT FOR UPDATE has no locking effect.
    changed = db.execute(update(StudySession).where(
        StudySession.id == session_id, StudySession.user_id == user_id,
        StudySession.revision == expected_revision, StudySession.status.in_(OPEN_STATUSES),
    ).values(status=status, revision=expected_revision + 1, updated_at=now,
             accumulated_milliseconds=total, last_activity_at=now if status == "active" else None,
             ended_at=now if status in ("completed", "abandoned") else None)
       .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Study session changed; reload before continuing")
    db.commit()
    db.refresh(row)
    return _project(row, now)


@router.post("/study-sessions/{session_id}/{action}", response_model=StudySessionResponse)
def change_session(session_id: UUID, action: StudyAction, payload: RevisionRequest, response: Response,
                   auth: tuple[User, AuthSession] = Depends(account_scoped_csrf), db: Session = Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    _no_store(response)
    throttle(db, scope="study_session_heartbeat" if action == "heartbeat" else "study_session_user",
             subject=str(user.id), limit=120 if action == "heartbeat" else 60)
    return _transition(db, user.id, session_id, action, payload.expected_revision, _utc_now())
