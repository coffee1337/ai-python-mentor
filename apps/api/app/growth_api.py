"""Growth surface: the flags a client may see and the operator's metrics.

A learner only ever reads their own flags. Writing an override is an admin action
and is audited; the analytics summary is admin-only because it aggregates accounts.
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app import analytics, feature_flags
from app.accounts_api import admin_auth, admin_csrf
from app.auth import current_auth
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


@router.get("/admin/analytics/events/{user_id}")
def user_events(user_id: UUID, auth=Depends(admin_auth), db: Session = Depends(get_db)) -> dict:
    return {"events": analytics.events_for(db, user_id)}


@router.get("/admin/analytics/export")
def analytics_export(days: int = 30, auth=Depends(admin_auth), db: Session = Depends(get_db)) -> dict:
    """Machine-readable export for a dashboard; same aggregation as the summary."""
    return {"generated_from": "product_events", "summary": analytics.summary(db, days=days)}


def _log(name: str, payload: dict) -> None:
    logger.info(json.dumps({"event": name, **payload}, sort_keys=True))
