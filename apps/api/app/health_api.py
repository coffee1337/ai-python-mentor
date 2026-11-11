"""Readiness reports infrastructure availability without exposing secrets."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from pathlib import Path
from functools import lru_cache
from alembic.script import ScriptDirectory
from app.db.session import get_db

router = APIRouter(tags=["health"])

@lru_cache(maxsize=1)
def expected_revision():
    return ScriptDirectory(str(Path(__file__).parents[1] / "migrations")).get_current_head()

@router.get("/metrics", include_in_schema=False)
def metrics_endpoint(db: Session = Depends(get_db)) -> Response:
    """Prometheus exposition. Counters only; no identifiers or content."""
    from app import metrics

    try:
        db.execute(text("SELECT 1"))
        metrics.DB_UP.set(1)
        pending = db.execute(text(
            "SELECT count(*) FROM execution_jobs WHERE status IN ('queued','running')"
        )).scalar_one()
        metrics.QUEUE_DEPTH.set(int(pending or 0))
    except Exception:
        metrics.DB_UP.set(0)
    body, content_type = metrics.render()
    return Response(content=body, media_type=content_type, headers={"Cache-Control": "no-store"})


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        # A live DB with an unapplied schema must not pass readiness.
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != expected_revision():
            raise ValueError()
    except Exception:
        raise HTTPException(503, "Application schema is not ready") from None
    return {"status": "ready"}
