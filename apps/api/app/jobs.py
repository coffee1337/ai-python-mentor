"""Durable dispatcher: python -m app.jobs. Never evaluates learner source.

Expired running claims are reconciled with exactly the same worker key. The
worker journal, rather than HTTP retry delivery, enforces at-most-once launch.
"""
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select
from app.db.job_models import ExecutionJob
from app.db.models import CodingAttempt, ExerciseVersion, User
from app.db.session import SessionLocal
from app.practice import _persist_result_and_evidence, _unavailable_result
from app.runner import RunnerError, RunnerUnavailable, runner

def dispatch_one(session_factory=SessionLocal):
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        job = db.scalar(select(ExecutionJob).where(
            (ExecutionJob.status == "queued") | ((ExecutionJob.status == "running") & (ExecutionJob.lease_expires_at < now))
        ).order_by(ExecutionJob.created_at).with_for_update(skip_locked=True).limit(1))
        if job is None:
            return False
        # User lock shared with API admission guarantees <=1 running job/user.
        db.scalar(select(User).where(User.id == job.user_id).with_for_update())
        other = db.scalar(select(ExecutionJob.id).where(ExecutionJob.user_id == job.user_id, ExecutionJob.id != job.id,
                          ExecutionJob.status == "running", ExecutionJob.lease_expires_at >= now).limit(1))
        if other is not None:
            return False
        attempt = db.get(CodingAttempt, job.coding_attempt_id)
        version = db.get(ExerciseVersion, attempt.exercise_version_id)
        expires = job.expires_at.replace(tzinfo=timezone.utc) if job.expires_at.tzinfo is None else job.expires_at
        if job.status == "queued" and expires <= now or job.status == "running" and expires + timedelta(seconds=120) <= now:
            job.status = "unavailable"
            _persist_result_and_evidence(db, attempt, _unavailable_result("Истёк срок ожидания задания; код не выполнялся."))
            return True
        token = str(uuid4())
        job.claim_token = token
        job.status = "running"
        job.lease_expires_at = now + timedelta(seconds=90)
        job_id, attempt_id = job.id, attempt.id
        exercise_id, version_number, source = attempt.exercise_id, version.version, attempt.source_code
        db.commit()
    # No database lock or connection is held over network IO.
    try:
        result = runner.run(exercise_id=exercise_id, exercise_version=version_number,
                            source_code=source, language="python", mode="function", idempotency_key=str(attempt_id), allow_in_progress=True)
    except (RunnerUnavailable, RunnerError, TimeoutError):
        result = _unavailable_result("Worker не подтвердил результат; зачёт не начислен.")
    except Exception:
        result = _unavailable_result("Worker недоступен; зачёт не начислен.")
    with session_factory() as db:
        job = db.scalar(select(ExecutionJob).where(ExecutionJob.id == job_id).with_for_update())
        if job is None or job.status != "running" or job.claim_token != token:
            return True
        attempt = db.get(CodingAttempt, attempt_id)
        if result.status == "in_progress":
            # Poll the same durable worker claim, never issue a fresh execution key.
            job.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=2)
            db.commit()
            return True
        job.status = "unavailable" if result.status == "unavailable" else "finished" if result.status in {"passed", "failed"} else "failed"
        job.claim_token = None
        job.lease_expires_at = None
        _persist_result_and_evidence(db, attempt, result)
    return True

def main():
    while True:
        try:
            if not dispatch_one():
                time.sleep(1)
        except Exception:
            # Only a code; source, exception/SQL details and credentials are private.
            print("execution_dispatch_unavailable", flush=True)
            time.sleep(2)

if __name__ == "__main__":
    main()
