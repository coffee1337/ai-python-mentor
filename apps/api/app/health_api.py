"""Readiness reports infrastructure availability without exposing secrets."""
from fastapi import APIRouter, Depends, HTTPException
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
