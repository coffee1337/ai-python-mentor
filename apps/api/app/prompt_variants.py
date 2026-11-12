"""Prompt variants: a version in config, a stable split per user, metrics compared.

A prompt change is a product change, so it ships as a named version, not as an edit
in place: the version that produced an answer is recorded with the usage row, and the
operator can compare latency, cost and feedback between variants.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "prompts.json"


class PromptConfigError(RuntimeError):
    pass


def _path() -> Path:
    return Path(os.getenv("PROMPT_VERSIONS_FILE", str(DEFAULT_CONFIG)))


def catalogue() -> dict:
    path = _path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PromptConfigError("Prompt version file is missing or invalid") from error
    if not isinstance(payload, dict) or not payload:
        raise PromptConfigError("Prompt version file is empty")
    return payload


def variants(task: str) -> list[str]:
    entry = catalogue().get(task)
    if not isinstance(entry, dict):
        return []
    versions = entry.get("versions")
    return [str(item) for item in versions] if isinstance(versions, list) and versions else []


def active(task: str) -> str:
    entry = catalogue().get(task) or {}
    version = entry.get("active")
    if not isinstance(version, str) or version not in variants(task):
        raise PromptConfigError(f"Active prompt version for {task} is not in its variants")
    return version


def _bucket(user_id: UUID | None, task: str) -> int:
    if user_id is None:
        return 0
    digest = hashlib.sha256(f"prompt:{task}:{user_id}".encode()).hexdigest()
    return int(digest[:8], 16) % 100


def for_user(task: str, user_id: UUID | None) -> str:
    """A stable split: a user never flips between variants of the same task."""
    versions = variants(task)
    if not versions:
        raise PromptConfigError(f"Unknown task {task}")
    if len(versions) == 1:
        return versions[0]
    entry = catalogue()[task]
    share = int(entry.get("rollout_percent", 50))
    return versions[1] if _bucket(user_id, task) < share else versions[0]


def instructions(task: str, version: str) -> str:
    """Extra instruction block for a variant; the trusted base prompt is unchanged."""
    entry = catalogue().get(task) or {}
    blocks = entry.get("instructions") or {}
    block = blocks.get(version)
    return str(block) if isinstance(block, str) else ""


def comparison(db: Session, *, days: int = 30) -> list[dict]:
    """Per-variant latency and cost from the usage ledger, plus tutor feedback rate."""
    from datetime import UTC, datetime, timedelta

    from app.db.models import AIFeedback, AIUsageLedger

    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
    rows = db.execute(
        select(
            AIUsageLedger.prompt_version,
            func.count(),
            func.avg(AIUsageLedger.latency_ms),
            func.sum(AIUsageLedger.input_tokens),
            func.sum(AIUsageLedger.output_tokens),
        )
        .where(AIUsageLedger.created_at >= since)
        .group_by(AIUsageLedger.prompt_version)
    ).all()
    helpful = dict(
        db.execute(
            select(AIFeedback.helpful, func.count()).where(AIFeedback.created_at >= since).group_by(AIFeedback.helpful)
        ).all()
    )
    return [
        {
            "prompt_version": version or "unversioned",
            "calls": int(count),
            "avg_latency_ms": round(float(latency), 1) if latency is not None else None,
            "input_tokens": int(prompt_tokens or 0),
            "output_tokens": int(completion_tokens or 0),
        }
        for version, count, latency, prompt_tokens, completion_tokens in rows
    ] + [{"feedback": {"helpful": int(helpful.get(True, 0)), "not_helpful": int(helpful.get(False, 0))}}]
