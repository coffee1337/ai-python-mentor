"""Product events: one table, one emit helper, metrics computed from facts.

Events are written by the code path that already changed state (registration,
onboarding, lesson completion, a graded run), so a metric cannot claim something
the product did not do. Props never carry source code, e-mail or free text.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ProductEvent, User

MAX_PROP_BYTES = 1024
ALLOWED_KEYS = {"lesson_id", "exercise_id", "skill_id", "status", "channel", "score", "level", "source"}


def emit(db: Session, *, user_id: UUID | None, name: str, **props) -> None:
    """Record one event. Unknown props are dropped, never stored blindly."""
    clean = {
        key: value for key, value in props.items()
        if key in ALLOWED_KEYS and isinstance(value, (str, int, float, bool)) and len(str(value)) <= 120
    }
    db.add(ProductEvent(id=uuid4(), user_id=user_id, name=name[:64], props=clean, created_at=datetime.now(UTC)))


def summary(db: Session, *, days: int = 30, now: datetime | None = None) -> dict:
    """North Star and the funnel, each number derived from stored events."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    counts = dict(
        db.execute(
            select(ProductEvent.name, func.count()).where(ProductEvent.created_at >= since).group_by(ProductEvent.name)
        ).all()
    )
    registered = counts.get("user_registered", 0)
    activated = counts.get("onboarding_completed", 0)
    first_lesson = counts.get("lesson_completed", 0)
    runs = counts.get("coding_graded", 0)
    tutor = counts.get("tutor_message", 0)

    cohorts = db.scalar(
        select(func.count(func.distinct(ProductEvent.user_id))).where(
            ProductEvent.created_at >= since, ProductEvent.name == "lesson_completed"
        )
    ) or 0
    returning = db.scalar(
        select(func.count(func.distinct(ProductEvent.user_id))).where(
            ProductEvent.created_at >= now - timedelta(days=7), ProductEvent.name == "session_started"
        )
    ) or 0
    total_users = db.scalar(select(func.count()).select_from(User)) or 0

    def rate(part: int | float, whole: int | float) -> float:
        return round(part / whole, 3) if whole else 0.0

    return {
        "window_days": days,
        "north_star": {"weekly_active_learners": cohorts},
        "acquisition": {"registered": registered, "total_accounts": int(total_users)},
        "activation": {"completed_onboarding": activated, "rate": rate(activated, registered)},
        "engagement": {"lessons_completed": first_lesson, "coding_runs": runs, "tutor_messages": tutor},
        "retention": {"active_last_7_days": returning, "rate": rate(returning, int(total_users))},
        "learning": {
            "lessons_per_registered_user": rate(first_lesson, registered),
            "runs_per_active_learner": rate(runs, cohorts),
        },
    }


def events_for(db: Session, user_id: UUID, *, limit: int = 100) -> list[dict]:
    rows = db.scalars(
        select(ProductEvent).where(ProductEvent.user_id == user_id).order_by(ProductEvent.created_at.desc()).limit(limit)
    ).all()
    return [
        {"name": row.name, "props": row.props, "created_at": row.created_at.isoformat()}
        for row in rows
    ]
