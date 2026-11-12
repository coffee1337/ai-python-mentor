"""Learner feedback on answers, and confidence before a check.

Feedback is a signal about the tutor, not about the learner: it is one vote per
answer, it can be changed, and the reasons are aggregated for the operator instead
of being shown back to anyone. Confidence is self-report; the product compares it
with the actual result and says so when they diverge.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts_api import admin_auth
from app.auth import csrf_protected, current_auth
from app.db.models import (
    AIFeedback,
    ConfidenceReport,
    KnowledgeCheckAttempt,
    MentorConversation,
    MentorMessage,
)
from app.db.session import get_db

router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    helpful: bool
    reason: str | None = Field(default=None, max_length=280)


class ConfidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence: int = Field(ge=1, le=5)


def _owned_answer(db: Session, user_id: UUID, message_id: UUID) -> MentorMessage:
    message = db.get(MentorMessage, message_id)
    conversation = db.get(MentorConversation, message.conversation_id) if message else None
    if message is None or conversation is None or conversation.user_id != user_id or message.role != "assistant":
        raise HTTPException(404, "Answer not found")
    return message


@router.post("/learning/mentor/messages/{message_id}/feedback", status_code=201)
def leave_feedback(message_id: UUID, payload: FeedbackRequest,
                   auth=Depends(csrf_protected), db: Session = Depends(get_db)) -> dict:
    user, _ = auth
    _owned_answer(db, user.id, message_id)
    row = db.scalar(select(AIFeedback).where(AIFeedback.message_id == message_id))
    if row is None:
        row = AIFeedback(id=uuid4(), user_id=user.id, message_id=message_id,
                         helpful=payload.helpful, reason=(payload.reason or "").strip() or None,
                         created_at=datetime.now(UTC))
        db.add(row)
    else:
        row.helpful = payload.helpful
        row.reason = (payload.reason or "").strip() or None
    db.commit()
    return {"message_id": str(message_id), "helpful": row.helpful}


@router.get("/learning/mentor/messages/{message_id}/feedback")
def my_feedback(message_id: UUID, auth=Depends(current_auth), db: Session = Depends(get_db)) -> dict:
    user, _ = auth
    _owned_answer(db, user.id, message_id)
    row = db.scalar(select(AIFeedback).where(AIFeedback.message_id == message_id))
    return {"message_id": str(message_id), "helpful": row.helpful if row else None,
            "reason": row.reason if row else None}


@router.get("/admin/analytics/feedback")
def feedback_summary(days: int = 30, auth=Depends(admin_auth), db: Session = Depends(get_db)) -> dict:
    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
    rows = db.execute(
        select(AIFeedback.helpful, func.count()).where(AIFeedback.created_at >= since).group_by(AIFeedback.helpful)
    ).all()
    counts = {bool(helpful): int(count) for helpful, count in rows}
    total = sum(counts.values())
    reasons = db.execute(
        select(AIFeedback.reason, func.count()).where(
            AIFeedback.created_at >= since, AIFeedback.helpful.is_(False), AIFeedback.reason.is_not(None)
        ).group_by(AIFeedback.reason).order_by(func.count().desc()).limit(10)
    ).all()
    return {
        "window_days": days,
        "helpful": counts.get(True, 0),
        "not_helpful": counts.get(False, 0),
        "total": total,
        "helpful_rate": round(counts.get(True, 0) / total, 3) if total else None,
        "reasons": [{"reason": reason, "count": int(count)} for reason, count in reasons],
    }


@router.post("/learning/lessons/{lesson_id}/confidence", status_code=201)
def report_confidence(lesson_id: str, payload: ConfidenceRequest,
                      auth=Depends(csrf_protected), db: Session = Depends(get_db)) -> dict:
    user, _ = auth
    from app.learning import accessible_lesson

    accessible_lesson(lesson_id, db, user)
    db.add(ConfidenceReport(id=uuid4(), user_id=user.id, lesson_id=lesson_id,
                            confidence=payload.confidence, created_at=datetime.now(UTC)))
    db.commit()
    return {"lesson_id": lesson_id, "confidence": payload.confidence}


@router.get("/learning/lessons/{lesson_id}/confidence")
def calibration(lesson_id: str, auth=Depends(current_auth), db: Session = Depends(get_db)) -> dict:
    """Compare the last self-report with the applied result and name the gap."""
    user, _ = auth
    report = db.scalar(
        select(ConfidenceReport)
        .where(ConfidenceReport.user_id == user.id, ConfidenceReport.lesson_id == lesson_id)
        .order_by(ConfidenceReport.created_at.desc())
    )
    if report is None:
        return {"lesson_id": lesson_id, "confidence": None, "verdict": None}
    attempt = db.scalar(
        select(KnowledgeCheckAttempt)
        .where(KnowledgeCheckAttempt.user_id == user.id, KnowledgeCheckAttempt.lesson_id == lesson_id)
        .order_by(KnowledgeCheckAttempt.created_at.desc())
    )
    if attempt is None:
        return {"lesson_id": lesson_id, "confidence": report.confidence, "verdict": "pending"}
    confident = report.confidence >= 4
    if confident and not attempt.passed:
        verdict = "overconfident"
        message = "Вы были уверены, но проверка не прошла: стоит разобрать тему заново."
    elif not confident and attempt.passed:
        verdict = "underconfident"
        message = "Вы сомневались, а проверка прошла: опирайтесь на результат, а не на ощущение."
    else:
        verdict = "aligned"
        message = "Самооценка совпала с результатом проверки."
    return {
        "lesson_id": lesson_id,
        "confidence": report.confidence,
        "score": attempt.score,
        "passed": attempt.passed,
        "verdict": verdict,
        "message": message,
    }
