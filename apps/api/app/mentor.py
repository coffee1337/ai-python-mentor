from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import ai_gateway
from app.auth import csrf_protected, current_auth
from app.db.models import AIUsageLedger, AuthSession, MentorConversation, MentorMessage, User
from app.db.session import get_db
from app.exercise_snapshots import snapshot_skill_id
from app.knowledge_base import (
    DEGRADED_ERRORS,
    KnowledgeBaseError,
    query_embedding,
    retrieval_messages,
    retrieve,
)
from app.learning import accessible_lesson
from app.mentor_prompts import context_messages

router = APIRouter(prefix="/learning", tags=["mentor"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value.strip()


class ChatMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    role: str
    content: str
    status: str
    created_at: datetime


def owned_conversation(db: Session, user: User, lesson_id: str):
    return db.scalar(select(MentorConversation).where(
        MentorConversation.user_id == user.id, MentorConversation.lesson_id == lesson_id))


def _usage_token(usage: dict | None, key: str) -> int | None:
    value = usage.get(key) if isinstance(usage, dict) else None
    return value if type(value) is int else None


def _record_usage(
    db: Session,
    user: User,
    *,
    model_id: str,
    messages: list[dict[str, str]],
    output: str,
    usage: dict | None,
    cache_hit: bool,
    status: str,
) -> None:
    db.add(AIUsageLedger(
        user_id=user.id,
        generation_id=None,
        operation="mentor_chat",
        model_id=model_id,
        cache_hit=cache_hit,
        input_chars=sum(len(message["content"]) for message in messages),
        output_chars=len(output),
        input_tokens=_usage_token(usage, "prompt_tokens"),
        output_tokens=_usage_token(usage, "completion_tokens"),
        status=status,
    ))


def _cached_model_id() -> str:
    try:
        return ai_gateway.configuration().model
    except ai_gateway.GatewayError:
        return "unconfigured"


def _retrieval_context(db: Session, lesson_id: str, message: str) -> list[dict[str, str]]:
    """Build the knowledge-base message for one turn, or nothing.

    Retrieval is scoped to the exact exercise version the learner is being
    shown and to that lesson's own skill. Any failure degrades to an empty
    list: the mentor keeps answering from lesson context alone, and no
    retrieved text is ever treated as an instruction.
    """
    try:
        from app.learning import _persisted_lesson_version

        version = _persisted_lesson_version(lesson_id, db)
        snapshot = version.content_snapshot
        if not isinstance(snapshot, dict):
            return []
        skill_id = snapshot_skill_id(
            snapshot, exercise_id=lesson_id, version=version.version,
        )
        vector = query_embedding(message)
        chunks = retrieve(
            db,
            exercise_version_id=version.id,
            skill_id=skill_id,
            query_vector=vector,
        )
        return retrieval_messages(chunks, skill_id=skill_id)
    except (HTTPException, KnowledgeBaseError, DEGRADED_ERRORS, SQLAlchemyError):
        # Degraded mode: retrieval is an enhancement, never a dependency. The
        # learner still gets a mentor answer, just without retrieved excerpts.
        return []


@router.get("/lessons/{lesson_id}/chat", response_model=list[ChatMessage])
def history(lesson_id: str, before: datetime | None = None,
            auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    accessible_lesson(lesson_id, db, auth[0])
    conversation = owned_conversation(db, auth[0], lesson_id)
    if conversation is None:
        return []
    query = select(MentorMessage).where(MentorMessage.conversation_id == conversation.id)
    if before:
        query = query.where(MentorMessage.created_at < before)
    return list(reversed(list(db.scalars(query.order_by(MentorMessage.created_at.desc()).limit(50)))))


@router.post("/lessons/{lesson_id}/chat", response_model=ChatMessage)
def chat(lesson_id: str, payload: ChatRequest,
         auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    user, _ = auth
    lesson = accessible_lesson(lesson_id, db, user)
    # Serialize per-user sends across PostgreSQL workers, including explicit retries.
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    conversation = owned_conversation(db, user, lesson_id)
    existing = db.get(MentorMessage, payload.request_id)
    if existing:
        if conversation is None or existing.conversation_id != conversation.id or existing.role != "user":
            raise HTTPException(404, "Message not found")
        if existing.content != payload.message:
            raise HTTPException(409, "Request ID already used for another message")
        if existing.status == "completed":
            assistant = db.scalar(select(MentorMessage).where(MentorMessage.reply_to_id == existing.id))
            _record_usage(
                db,
                user,
                model_id=_cached_model_id(),
                messages=[{"role": "user", "content": payload.message}],
                output=assistant.content,
                usage=None,
                cache_hit=True,
                status="cache_hit",
            )
            db.commit()
            return assistant
    now = datetime.now(timezone.utc)
    count = db.scalar(select(func.coalesce(func.sum(MentorMessage.attempt_count), 0))
        .join(MentorConversation, MentorMessage.conversation_id == MentorConversation.id)
        .where(MentorConversation.user_id == user.id,
               MentorMessage.last_attempt_at >= now - timedelta(minutes=1)))
    if count >= 5:
        raise HTTPException(429, "Too many mentor messages; retry in one minute", headers={"Retry-After": "60"})
    if conversation is None:
        conversation = MentorConversation(user_id=user.id, lesson_id=lesson_id)
        db.add(conversation)
        db.flush()
    if existing is None:
        existing = MentorMessage(id=payload.request_id, conversation_id=conversation.id,
                                 role="user", content=payload.message, status="failed",
                                 attempt_count=0, created_at=now)
        db.add(existing)
    existing.attempt_count += 1
    existing.last_attempt_at = now
    db.flush()
    prior = list(reversed(list(db.scalars(select(MentorMessage).where(
        MentorMessage.conversation_id == conversation.id,
        MentorMessage.status == "completed",
        MentorMessage.id != existing.id,
    ).order_by(MentorMessage.created_at.desc()).limit(6)))))
    messages = context_messages(lesson, user.profile.experience_level)
    messages += [{"role": message.role, "content": message.content} for message in prior]
    messages.append({"role": "user", "content": payload.message})
    # Reference material goes in as data after the learner turn, never as
    # instructions and never with another skill's or another version's text.
    messages[2:2] = _retrieval_context(db, lesson_id, payload.message)
    config = None
    try:
        config = ai_gateway.configuration()
        answer, usage = ai_gateway.generate_with_usage(config, messages)
    except ai_gateway.GatewayError as exc:
        existing.status = "failed"
        _record_usage(
            db,
            user,
            model_id=config.model if config is not None else "unconfigured",
            messages=messages,
            output="",
            usage=None,
            cache_hit=False,
            status="gateway_error",
        )
        db.commit()
        raise HTTPException(exc.status, exc.detail) from None
    _record_usage(
        db,
        user,
        model_id=config.model,
        messages=messages,
        output=answer,
        usage=usage,
        cache_hit=False,
        status="completed",
    )
    existing.status = "completed"
    assistant = MentorMessage(conversation_id=conversation.id, role="assistant", content=answer,
                              status="completed", reply_to_id=existing.id,
                              created_at=datetime.now(timezone.utc))
    db.add(assistant)
    db.commit()
    db.refresh(assistant)
    return assistant
