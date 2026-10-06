"""Owned durable Python submissions, with opaque retry keys and bounded queues."""
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import csrf_protected, current_auth
from app.db.models import AuthSession, CodingAttempt, User
from app.db.job_models import ExecutionJob
from app.db.session import get_db
from app.learning import coding_practice_ready, require_onboarding
from app.practice import AttemptRequest, _persist_result_and_evidence, _unavailable_result
from app.runner import PROTOCOL_VERSION, RunnerUnavailable, configuration

router = APIRouter(prefix="/learning", tags=["execution-jobs"])
ACTIVE = ("queued", "running")
KEY = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

class JobResponse(BaseModel):
    id: UUID
    attempt_id: UUID
    exercise_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    result: dict

def execution_configured():
    if os.getenv("EXECUTION_JOBS_ENABLED", "false").casefold() != "true":
        return False
    try:
        configuration()
        return True
    except RunnerUnavailable:
        return False

@router.get("/execution-capabilities")
def capabilities(auth=Depends(current_auth)):
    configured = execution_configured()
    return {"configured": configured, "protocol_version": PROTOCOL_VERSION, "async_jobs": True,
            "message": "Задания выполняются отдельным worker." if configured else "Изолированное выполнение не настроено; код можно сохранить."}

@router.get("/exercises/{lesson_id}/coding-specification")
def coding_specification(lesson_id: str, auth=Depends(current_auth), db: Session=Depends(get_db)):
    from app.coding_exercises import resolve_coding_exercise
    require_onboarding(auth[0])
    if not coding_practice_ready(db, auth[0]):
        raise HTTPException(409, "Сначала изучите функции, параметры, возврат значений и словари. Сейчас доступна практика чтения и проверка понимания.")
    contract, version = resolve_coding_exercise(db, auth[0], f"{lesson_id}-code")
    db.commit()
    return {"exercise_id": version.exercise_id, "lesson_id": contract["lesson_id"], "version": version.version,
            "prompt": contract["prompt"], "starter_code": contract["starter_code"], "function_name": "solve",
            "public_examples": [{"args": case["args"], "kwargs": case["kwargs"], "expected": case["expected"]}
                                for case in contract["cases"] if case["visibility"] == "public"]}

def job_response(db, job):
    attempt = db.get(CodingAttempt, job.coding_attempt_id)
    return JobResponse(id=job.id, attempt_id=attempt.id, exercise_id=attempt.exercise_id, status=job.status,
                       created_at=job.created_at, updated_at=job.updated_at, result=json.loads(attempt.result or "{}"))

def owned_job(db, user, job_id):
    job = db.scalar(select(ExecutionJob).where(ExecutionJob.id == job_id, ExecutionJob.user_id == user.id))
    if job is None:
        raise HTTPException(404, "Job not found")
    return job

@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID, auth=Depends(current_auth), db: Session=Depends(get_db)):
    return job_response(db, owned_job(db, auth[0], job_id))

@router.post("/exercises/{exercise_id}/jobs", response_model=JobResponse, status_code=202)
def enqueue(exercise_id: str, payload: AttemptRequest, response: Response,
            idempotency_key: str=Header(alias="Idempotency-Key"), auth=Depends(csrf_protected), db: Session=Depends(get_db)):
    result = enqueue_owned(db, auth[0], exercise_id, payload, idempotency_key)
    response.headers["Location"] = f"/learning/jobs/{result.id}"
    return result

def enqueue_owned(db: Session, user: User, exercise_id: str, payload: AttemptRequest,
                  idempotency_key: str, *, bound_version=None) -> JobResponse:
    """Shared admission for authored and exact-version generated step bindings."""
    from app.coding_exercises import resolve_coding_exercise
    require_onboarding(user)
    if not KEY.fullmatch(idempotency_key):
        raise HTTPException(422, "Invalid idempotency key")
    if payload.language != "python" or payload.mode != "function" or len(payload.source_code.encode()) > 64 * 1024:
        raise HTTPException(422, "Only bounded Python function submissions are supported")
    digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
    body = hashlib.sha256(json.dumps([exercise_id, payload.model_dump()], sort_keys=True).encode()).hexdigest()
    if db.get_bind().dialect.name == "postgresql":
        # Serialize the global bounded queue without holding this lock at execution.
        db.execute(text("SELECT pg_advisory_xact_lock(1738241947)"))
    # Serialize admission per user across API workers on PostgreSQL.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    existing = db.scalar(select(ExecutionJob).where(ExecutionJob.user_id == user.id, ExecutionJob.request_key_digest == digest))
    if existing is not None:
        if existing.body_digest != body:
            raise HTTPException(409, "Idempotency key was used with a different submission")
        return job_response(db, existing)
    item, version = resolve_coding_exercise(db, user, exercise_id, bound_version=bound_version)
    now = datetime.now(timezone.utc)
    if db.scalar(select(func.count()).select_from(ExecutionJob).where(ExecutionJob.user_id == user.id, ExecutionJob.created_at > now - timedelta(minutes=1))) >= 6:
        raise HTTPException(429, "Too many submissions; try again later")
    if db.scalar(select(func.count()).select_from(ExecutionJob).where(ExecutionJob.user_id == user.id, ExecutionJob.status.in_(ACTIVE))) >= 3:
        raise HTTPException(429, "Your submission queue is full")
    if db.scalar(select(func.count()).select_from(ExecutionJob).where(ExecutionJob.status.in_(ACTIVE))) >= 64:
        raise HTTPException(429, "Submission queue is full")
    enabled = execution_configured()
    attempt = CodingAttempt(user_id=user.id, exercise_id=exercise_id, exercise_version_id=version.id,
                            language="python", mode="function", source_code=payload.source_code,
                            status="queued" if enabled else "unavailable", result="{}")
    db.add(attempt); db.flush()
    job = ExecutionJob(user_id=user.id, coding_attempt_id=attempt.id, request_key_digest=digest, body_digest=body,
                       status="queued" if enabled else "unavailable", expires_at=now + timedelta(seconds=60))
    db.add(job)
    try:
        if not enabled:
            _persist_result_and_evidence(db, attempt, _unavailable_result("Код сохранён; изолированный worker не настроен."))
        else:
            db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(ExecutionJob).where(ExecutionJob.user_id == user.id, ExecutionJob.request_key_digest == digest))
        if existing is None or existing.body_digest != body:
            raise HTTPException(409, "Concurrent submission conflict") from None
        job = existing
    db.refresh(job)
    return job_response(db, job)

@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel(job_id: UUID, auth=Depends(csrf_protected), db: Session=Depends(get_db)):
    job = owned_job(db, auth[0], job_id)
    db.refresh(job, with_for_update=True)
    if job.status == "running":
        raise HTTPException(409, "Running jobs stop at the worker deadline; cancellation cannot be confirmed yet")
    if job.status == "queued":
        job.status = "cancelled"
        attempt = db.get(CodingAttempt, job.coding_attempt_id)
        _persist_result_and_evidence(db, attempt, _unavailable_result("Отправка отменена до выполнения."))
    return job_response(db, job)
