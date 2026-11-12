"""Feature flags: a fixed catalogue, a deterministic rollout, an audited override.

Flags gate features that exist but are not on for everyone. The rollout is a hash
of user id and flag name, so a user never flips between requests and no state has to
be stored. An override is per user, audited, and read before the percentage rule.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FeatureFlagOverride

CATALOGUE = {
    "github_import": "Импорт репозитория GitHub",
    "large_repo_review": "Ревью большого репозитория",
    "new_tutor_v2": "Новый контур тьютора",
    "new_mastery_model": "Новая модель мастерства",
    "new_vacancy_parser": "Новый разбор вакансий",
}
DEFAULT_PERCENT = 0


def _configured_percent(flag: str) -> int:
    raw = os.getenv(f"FEATURE_{flag.upper()}_PERCENT", "").strip()
    if not raw:
        return DEFAULT_PERCENT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_PERCENT
    return max(0, min(100, value))


def bucket(user_id: UUID | str | None, flag: str) -> int:
    """Stable 0..99 bucket; the same user always lands in the same place."""
    if user_id is None:
        return 100
    digest = hashlib.sha256(f"{flag}:{user_id}".encode()).hexdigest()
    return int(digest[:8], 16) % 100


def enabled(db: Session, user_id: UUID | None, flag: str) -> bool:
    if flag not in CATALOGUE:
        return False
    override = db.get(FeatureFlagOverride, (flag, user_id)) if user_id is not None else None
    if override is not None:
        return override.enabled
    return bucket(user_id, flag) < _configured_percent(flag)


def snapshot(db: Session, user_id: UUID | None) -> dict[str, bool]:
    return {flag: enabled(db, user_id, flag) for flag in CATALOGUE}


def override(db: Session, *, flag: str, user_id: UUID, enabled_value: bool, actor_id: UUID) -> FeatureFlagOverride:
    if flag not in CATALOGUE:
        raise ValueError("unknown_flag")
    row = db.get(FeatureFlagOverride, (flag, user_id))
    if row is None:
        row = FeatureFlagOverride(flag=flag, user_id=user_id, enabled=enabled_value,
                                  updated_by=actor_id, updated_at=datetime.now(UTC))
        db.add(row)
    else:
        row.enabled = enabled_value
        row.updated_by = actor_id
        row.updated_at = datetime.now(UTC)
    db.flush()
    return row


def state(db: Session) -> list[dict]:
    rows = db.scalars(select(FeatureFlagOverride)).all()
    return [
        {
            "flag": flag,
            "title": title,
            "percent": _configured_percent(flag),
            "overrides": [
                {"user_id": str(row.user_id), "enabled": row.enabled, "updated_at": row.updated_at.isoformat()}
                for row in rows if row.flag == flag
            ],
        }
        for flag, title in CATALOGUE.items()
    ]


def audit_line(*, actor_id: UUID, flag: str, user_id: UUID, enabled_value: bool) -> str:
    """One machine-readable line for the operator log; no user data beyond ids."""
    return json.dumps({"event": "feature_flag_override", "actor": str(actor_id), "flag": flag,
                       "user": str(user_id), "enabled": enabled_value, "id": str(uuid4())})
