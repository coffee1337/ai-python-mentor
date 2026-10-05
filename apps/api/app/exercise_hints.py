"""Versioned authored hint ladders for the MVP lesson exercises."""

import hashlib
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import csrf_protected
from app.db.models import AuthSession, ExerciseHint, ExerciseVersion, HintReveal, KnowledgeCheckSession, LessonSession, User
from app.db.session import get_db
from app.exercise_snapshots import authored_snapshot, snapshot_hints
from app.learning import accessible_lesson
from app.learning_content import EXERCISE_HINT_LADDERS

router = APIRouter(prefix="/learning/exercises", tags=["learning"])


class HintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal[1, 2, 3, 4, 5]


class HintHeaders(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(
        alias="Idempotency-Key",
        min_length=1,
        max_length=200,
    )


def parse_hint_headers(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> HintHeaders:
    if idempotency_key is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Idempotency-Key header is required")
    return HintHeaders.model_validate({"Idempotency-Key": idempotency_key})


class HintResponse(BaseModel):
    level: int
    kind: Literal["direction", "concept", "step", "pseudocode", "solution"]
    text: str


def _persisted_idempotency_key(exercise_version_id, raw_key: str) -> str:
    """Namespace a client key while retaining the 0015 global DB unique."""
    return f"v16:{hashlib.sha256(f'{exercise_version_id}:{raw_key}'.encode('utf-8')).hexdigest()}"


def _legacy_replay(
    db: Session,
    *,
    user_id,
    exercise_version_id,
    level: int,
    raw_key: str,
) -> HintReveal | None:
    """Find a pre-0016 raw key only within its original reveal scope."""
    return db.scalar(
        select(HintReveal).where(
            HintReveal.user_id == user_id,
            HintReveal.exercise_version_id == exercise_version_id,
            HintReveal.level == level,
            HintReveal.idempotency_key == raw_key,
        )
    )


def _legacy_key_reused_with_different_level(
    db: Session,
    *,
    user_id,
    exercise_version_id,
    level: int,
    raw_key: str,
) -> bool:
    return db.scalar(
        select(HintReveal.id).where(
            HintReveal.user_id == user_id,
            HintReveal.exercise_version_id == exercise_version_id,
            HintReveal.idempotency_key == raw_key,
            HintReveal.level != level,
        )
    ) is not None


def _seed_exercise(
    db: Session,
    exercise_id: str,
    *,
    seed_hints: bool = True,
) -> ExerciseVersion:
    try:
        current_snapshot = authored_snapshot(exercise_id)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Exercise content snapshot is unavailable",
        ) from exc
    version_number = current_snapshot["version"]
    lesson_id = current_snapshot["lesson"]["id"] if current_snapshot["lesson"] else None
    try:
        with db.begin_nested():
            version = db.scalar(
                select(ExerciseVersion).where(
                    ExerciseVersion.exercise_id == exercise_id,
                    ExerciseVersion.version == version_number,
                )
            )
            if version is None:
                version = ExerciseVersion(
                    exercise_id=exercise_id,
                    version=version_number,
                    lesson_id=lesson_id,
                    content_snapshot=current_snapshot,
                )
                db.add(version)
                db.flush()
            elif version.lesson_id != lesson_id:
                raise HTTPException(status.HTTP_409_CONFLICT, "Exercise content version conflict")

            # Legacy/unknown rows have no trusted content to reconstruct.
            if version.content_snapshot is None:
                return version
            if not seed_hints:
                return version

            persisted_hints = snapshot_hints(version.content_snapshot)
            existing = {
                hint.level: hint
                for hint in db.scalars(
                    select(ExerciseHint).where(
                        ExerciseHint.exercise_version_id == version.id
                    )
                )
            }
            for level, kind, text in persisted_hints:
                hint = existing.get(level)
                if hint is None:
                    db.add(
                        ExerciseHint(
                            exercise_version_id=version.id,
                            level=level,
                            kind=kind,
                            content=text,
                        )
                    )
                elif hint.kind != kind or hint.content != text:
                    # Published content is immutable. A changed ladder must publish
                    # a new version instead of silently changing prior learner-visible text.
                    raise HTTPException(status.HTTP_409_CONFLICT, "Exercise content version conflict")
            db.flush()
    except IntegrityError as exc:
        # A concurrent request may have won the version/hint inserts. Only
        # accept the error when the committed row is now a complete, matching
        # authored ladder; unrelated integrity errors remain errors.
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        message = str(exc.orig)
        known_conflict = constraint in {"uq_exercise_version", "uq_exercise_hint_level"} or (
            "UNIQUE constraint failed:" in message
            and (
                "exercise_versions.exercise_id, exercise_versions.version" in message
                or "exercise_hints.exercise_version_id, exercise_hints.level" in message
            )
        )
        if not known_conflict:
            raise
        version = db.scalar(
            select(ExerciseVersion).where(
                ExerciseVersion.exercise_id == exercise_id,
                ExerciseVersion.version == version_number,
            )
        )
        if version is None or version.lesson_id != lesson_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Exercise content version conflict") from exc
        if version.content_snapshot is None:
            return version
        if not seed_hints:
            return version
        existing = {
            hint.level: hint
            for hint in db.scalars(
                select(ExerciseHint).where(
                    ExerciseHint.exercise_version_id == version.id
                )
            )
        }
        expected = {
            level: (kind, text)
            for level, kind, text in snapshot_hints(version.content_snapshot)
        }
        if set(existing) != set(expected) or any(
            existing[level].kind != kind or existing[level].content != text
            for level, (kind, text) in expected.items()
            if level in existing
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Exercise content version conflict") from exc
    return version


def _ensure_snapshot_hints(db: Session, version: ExerciseVersion) -> None:
    if not isinstance(version.content_snapshot, dict):
        raise HTTPException(status.HTTP_409_CONFLICT, "Exercise content version is unavailable")
    expected = snapshot_hints(version.content_snapshot)
    existing = {
        hint.level: hint
        for hint in db.scalars(
            select(ExerciseHint).where(ExerciseHint.exercise_version_id == version.id)
        )
    }
    if any(
        existing[level].kind != kind or existing[level].content != text
        for level, kind, text in expected
        if level in existing
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Exercise content version conflict")
    for level, kind, text in expected:
        if level not in existing:
            db.add(ExerciseHint(
                exercise_version_id=version.id, level=level, kind=kind, content=text,
            ))
    db.flush()


@router.post(
    "/{exercise_id}/hints",
    response_model=HintResponse,
    status_code=status.HTTP_200_OK,
)
def reveal_hint(
    exercise_id: str,
    payload: HintRequest,
    headers: HintHeaders = Depends(parse_hint_headers),
    auth: tuple[User, AuthSession] = Depends(csrf_protected),
    db: Session = Depends(get_db),
) -> HintResponse:
    user, _ = auth
    if exercise_id not in EXERCISE_HINT_LADDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found")
    pending_versions = set(db.scalars(
        select(LessonSession.exercise_version_id).where(
            LessonSession.user_id == user.id,
            LessonSession.lesson_id == exercise_id,
            LessonSession.consumed_at.is_(None),
        )
    )) | set(db.scalars(
        select(KnowledgeCheckSession.exercise_version_id).where(
            KnowledgeCheckSession.user_id == user.id,
            KnowledgeCheckSession.lesson_id == exercise_id,
            KnowledgeCheckSession.consumed_at.is_(None),
        )
    ))
    if len(pending_versions) > 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Conflicting exercise bindings")
    if pending_versions:
        version = db.get(ExerciseVersion, pending_versions.pop())
        if version is None or version.exercise_id != exercise_id or version.lesson_id != exercise_id or version.content_snapshot is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Exercise content version is unavailable")
        accessible_lesson(exercise_id, db, user, bound_version=version)
        _ensure_snapshot_hints(db, version)
    else:
        accessible_lesson(exercise_id, db, user)
        version = _seed_exercise(db, exercise_id)
    persisted_idempotency_key = _persisted_idempotency_key(version.id, headers.idempotency_key)

    existing_for_key = db.scalar(
        select(HintReveal).where(
            HintReveal.user_id == user.id,
            HintReveal.exercise_version_id == version.id,
            HintReveal.idempotency_key == persisted_idempotency_key,
        )
    )
    if existing_for_key is not None:
        if existing_for_key.level != payload.level:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key was reused with different parameters")
        hint = db.get(ExerciseHint, existing_for_key.hint_id)
        if hint is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Exercise hints are unavailable")
        return HintResponse(level=hint.level, kind=hint.kind, text=hint.content)

    legacy_replay = _legacy_replay(
        db,
        user_id=user.id,
        exercise_version_id=version.id,
        level=payload.level,
        raw_key=headers.idempotency_key,
    )
    if legacy_replay is not None:
        hint = db.get(ExerciseHint, legacy_replay.hint_id)
        if hint is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Exercise hints are unavailable")
        return HintResponse(level=hint.level, kind=hint.kind, text=hint.content)
    if _legacy_key_reused_with_different_level(
        db,
        user_id=user.id,
        exercise_version_id=version.id,
        level=payload.level,
        raw_key=headers.idempotency_key,
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key was reused with different parameters")

    revealed_levels = set(
        db.scalars(
            select(HintReveal.level).where(
                HintReveal.user_id == user.id,
                HintReveal.exercise_version_id == version.id,
            )
        )
    )
    next_level = max(revealed_levels, default=0) + 1
    if next_level > 5:
        raise HTTPException(status.HTTP_409_CONFLICT, "All hints have already been revealed")
    if payload.level != next_level:
        detail = "Hint level was already revealed" if payload.level <= max(revealed_levels, default=0) else "Reveal the next hint level first"
        raise HTTPException(status.HTTP_409_CONFLICT, detail)

    hint = db.scalar(
        select(ExerciseHint).where(
            ExerciseHint.exercise_version_id == version.id,
            ExerciseHint.level == payload.level,
        )
    )
    if hint is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Exercise hints are unavailable")
    db.add(
        HintReveal(
            user_id=user.id,
            exercise_version_id=version.id,
            hint_id=hint.id,
            level=hint.level,
            idempotency_key=persisted_idempotency_key,
            revealed_at=datetime.now(timezone.utc),
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        message = str(exc.orig)
        known_conflict = constraint in {
            "uq_hint_reveal_user_version_level",
            "uq_hint_reveal_idempotency",
        } or (
            "UNIQUE constraint failed:" in message
            and (
                "hint_reveals.user_id, hint_reveals.exercise_version_id, hint_reveals.level" in message
                or "hint_reveals.user_id, hint_reveals.exercise_version_id, hint_reveals.idempotency_key" in message
                or "hint_reveals.user_id, hint_reveals.idempotency_key" in message
            )
        )
        if not known_conflict:
            raise
        existing_for_key = db.scalar(
            select(HintReveal).where(
                HintReveal.user_id == user.id,
                HintReveal.exercise_version_id == version.id,
                HintReveal.idempotency_key == persisted_idempotency_key,
            )
        )
        if existing_for_key is not None and existing_for_key.level == payload.level:
            hint = db.get(ExerciseHint, existing_for_key.hint_id)
            if hint is not None:
                return HintResponse(level=hint.level, kind=hint.kind, text=hint.content)
        legacy_replay = _legacy_replay(
            db,
            user_id=user.id,
            exercise_version_id=version.id,
            level=payload.level,
            raw_key=headers.idempotency_key,
        )
        if legacy_replay is not None:
            hint = db.get(ExerciseHint, legacy_replay.hint_id)
            if hint is not None:
                return HintResponse(level=hint.level, kind=hint.kind, text=hint.content)
        raise HTTPException(status.HTTP_409_CONFLICT, "Hint level was already revealed") from exc
    return HintResponse(level=hint.level, kind=hint.kind, text=hint.content)
