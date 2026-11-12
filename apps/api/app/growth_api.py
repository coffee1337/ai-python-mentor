"""Growth surface: the flags a client may see and the operator's metrics.

A learner only ever reads their own flags. Writing an override is an admin action
and is audited; the analytics summary is admin-only because it aggregates accounts.
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import analytics, feature_flags, prompt_variants
from app.accounts_api import admin_auth, admin_csrf
from app.auth import csrf_protected, current_auth
from app.db.session import get_db

router = APIRouter(tags=["growth"])
logger = logging.getLogger("growth")


class OverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag: str
    user_id: UUID
    enabled: bool


@router.get("/me/features")
def my_features(auth=Depends(current_auth), db: Session = Depends(get_db)) -> dict:
    return {"flags": feature_flags.snapshot(db, auth[0].id)}


class InterestsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interests: list[str] = Field(default_factory=list, max_length=3)


@router.get("/me/interests")
def my_interests(auth=Depends(current_auth), db: Session = Depends(get_db)) -> dict:
    from app import interests

    return {"vocabulary": interests.VOCABULARY, "selected": interests.for_user(db, auth[0].id)}


@router.put("/me/interests")
def set_interests(payload: InterestsRequest, auth=Depends(csrf_protected), db: Session = Depends(get_db)) -> dict:
    """Interests change the example in a practice prompt, never the graded answer."""
    from app import interests

    try:
        selected = interests.set_for_user(db, auth[0].id, payload.interests)
    except interests.UnknownInterest:
        raise HTTPException(422, f"Допустимые интересы: {', '.join(interests.VOCABULARY)}") from None
    except LookupError:
        raise HTTPException(409, "Сначала завершите онбординг") from None
    db.commit()
    return {"selected": selected, "scenario": interests.scenario(selected)}


@router.get("/admin/analytics/interests")
def interests_demand(auth=Depends(admin_auth), db: Session = Depends(get_db)) -> dict:
    from app import interests

    return {"counts": interests.counts(db)}


@router.get("/me/memory")
def my_memory(lesson_id: str | None = None, auth=Depends(current_auth), db: Session = Depends(get_db)) -> dict:
    """What the product remembers about this learner: counts, not a transcript."""
    from app import memory

    profile = memory.behavioural_profile(db, user=auth[0])
    if not lesson_id:
        return {"profile": profile, "dialogue": None}
    summary = memory.interaction_summary(db, user_id=auth[0].id, lesson_id=lesson_id)
    return {"profile": profile, "dialogue": summary.as_dict()}


@router.get("/admin/features")
def flags_state(auth=Depends(admin_auth), db: Session = Depends(get_db)) -> dict:
    return {"catalogue": feature_flags.CATALOGUE, "flags": feature_flags.state(db)}


@router.post("/admin/features")
def set_flag(payload: OverrideRequest, auth=Depends(admin_csrf), db: Session = Depends(get_db)) -> dict:
    try:
        row = feature_flags.override(db, flag=payload.flag, user_id=payload.user_id,
                                     enabled_value=payload.enabled, actor_id=auth[0].id)
    except ValueError:
        raise HTTPException(422, "Unknown feature flag") from None
    db.commit()
    logger.info(feature_flags.audit_line(actor_id=auth[0].id, flag=payload.flag,
                                         user_id=payload.user_id, enabled_value=payload.enabled))
    return {"flag": row.flag, "user_id": str(row.user_id), "enabled": row.enabled}


@router.get("/admin/analytics")
def analytics_summary(days: int = 30, auth=Depends(admin_auth), db: Session = Depends(get_db)) -> dict:
    if not 1 <= days <= 365:
        raise HTTPException(422, "Window must be between 1 and 365 days")
    return analytics.summary(db, days=days)


@router.get("/admin/ai-eval")
def eval_history(limit: int = 10, auth=Depends(admin_auth), db: Session = Depends(get_db)) -> dict:
    from app import ai_eval

    return {"runs": ai_eval.history(db, limit=max(1, min(limit, 50)))}


@router.post("/admin/ai-eval/run", status_code=201)
def eval_run(auth=Depends(admin_csrf), db: Session = Depends(get_db)) -> dict:
    """Run the benchmark against the configured provider and store the numbers."""
    from app import ai_eval, ai_gateway

    try:
        config = ai_gateway.configuration(task="tutor_chat")
    except ai_gateway.GatewayError:
        raise HTTPException(503, "AI-провайдер не настроен: замер невозможен") from None
    row = ai_eval.run(db, config=config)
    return {"id": str(row.id), "score": row.score, "cases": row.cases,
            "metrics": {key: value for key, value in (row.metrics or {}).items() if key != "results"}}


@router.get("/admin/analytics/ai")
def ai_metrics(days: int = 7, auth=Depends(admin_auth), db: Session = Depends(get_db)) -> dict:
    """Latency and cost per operation, from the usage ledger."""
    from datetime import UTC, datetime, timedelta

    from app.db.models import AIUsageLedger

    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 90)))
    rows = db.execute(
        select(
            AIUsageLedger.operation,
            func.count(),
            func.avg(AIUsageLedger.latency_ms),
            func.sum(AIUsageLedger.input_tokens),
            func.sum(AIUsageLedger.output_tokens),
        )
        .where(AIUsageLedger.created_at >= since)
        .group_by(AIUsageLedger.operation)
    ).all()
    return {
        "window_days": days,
        "operations": [
            {
                "operation": operation,
                "calls": int(count),
                "avg_latency_ms": round(float(latency), 1) if latency is not None else None,
                "input_tokens": int(prompt_tokens or 0),
                "output_tokens": int(completion_tokens or 0),
            }
            for operation, count, latency, prompt_tokens, completion_tokens in rows
        ],
        "prompt_variants": [item for item in prompt_variants.comparison(db, days=days)
                            if "prompt_version" in item],
    }


@router.get("/admin/analytics/events/{user_id}")
def user_events(user_id: UUID, auth=Depends(admin_auth), db: Session = Depends(get_db)) -> dict:
    return {"events": analytics.events_for(db, user_id)}


@router.get("/admin/analytics/export")
def analytics_export(days: int = 30, auth=Depends(admin_auth), db: Session = Depends(get_db)) -> dict:
    """Machine-readable export for a dashboard; same aggregation as the summary."""
    return {"generated_from": "product_events", "summary": analytics.summary(db, days=days)}


def _log(name: str, payload: dict) -> None:
    logger.info(json.dumps({"event": name, **payload}, sort_keys=True))
