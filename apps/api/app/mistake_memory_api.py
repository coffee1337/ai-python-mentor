"""Read-only API for the authenticated learner's repeated mistakes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.auth import current_auth
from app.db.models import (
    AuthSession,
    MisconceptionVersion,
    User,
    UserMistake,
)
from app.db.session import get_db


class MistakeMemoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_text: str
    remediation_text: str
    remediation_exercise_id: str
    last_seen_at: datetime


router = APIRouter(prefix="/learning", tags=["mistake-memory"])


@router.get("/mistakes", response_model=list[MistakeMemoryResponse])
def get_mistakes(
    auth: tuple[User, AuthSession] = Depends(current_auth),
    db: Session = Depends(get_db),
) -> list[MistakeMemoryResponse]:
    """Return only repeated mistakes belonging to the authenticated learner."""

    user, _ = auth
    current_version = aliased(MisconceptionVersion)
    # The aggregate can outlive individual occurrence rows. Render it using
    # the latest authored remediation for its stable misconception code.
    latest_version = (
        select(func.max(current_version.version))
        .where(
            current_version.misconception_code
            == UserMistake.misconception_code
        )
        .correlate(UserMistake)
        .scalar_subquery()
    )
    rows = db.execute(
        select(
            MisconceptionVersion.error_text,
            MisconceptionVersion.remediation_text,
            MisconceptionVersion.remediation_exercise_id,
            UserMistake.last_seen_at,
        )
        .join(
            MisconceptionVersion,
            and_(
                MisconceptionVersion.misconception_code
                == UserMistake.misconception_code,
                MisconceptionVersion.version == latest_version,
            ),
        )
        .where(
            UserMistake.user_id == user.id,
            UserMistake.occurrence_count >= 2,
        )
        .order_by(
            UserMistake.last_seen_at.desc(),
            UserMistake.misconception_code.asc(),
        )
    ).all()
    return [MistakeMemoryResponse.model_validate(row._mapping) for row in rows]
