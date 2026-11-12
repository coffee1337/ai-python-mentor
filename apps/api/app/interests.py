"""Learner interests as a wrapper, never as a change of the task.

The vocabulary is closed, the effect is bounded: an interest can change the example
in the practice prompt (a scoreboard instead of a warehouse), never the graded
answer, the tests or the difficulty. With no interests chosen the text is unchanged.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User

VOCABULARY: dict[str, str] = {
    "games": "игры и таблицы очков",
    "finance": "личные финансы и бюджеты",
    "sport": "тренировки и результаты",
    "travel": "поездки и маршруты",
    "health": "здоровье и привычки",
}
MAX_INTERESTS = 3


class UnknownInterest(ValueError):
    pass


def normalize(values: list[str] | None) -> list[str]:
    """Validate against the closed vocabulary, keep order, drop duplicates."""
    if not values:
        return []
    cleaned: list[str] = []
    for raw in values:
        key = str(raw).strip().casefold()
        if key not in VOCABULARY:
            raise UnknownInterest(key)
        if key not in cleaned:
            cleaned.append(key)
    if len(cleaned) > MAX_INTERESTS:
        raise UnknownInterest("too_many")
    return cleaned


def scenario(values: list[str] | None) -> str | None:
    """One sentence the practice generator may use as the setting of the example."""
    if not values:
        return None
    first = VOCABULARY.get(values[0])
    if first is None:
        return None
    return f"Если уместно, возьми пример из области «{first}» — но условие и проверка не меняются."


def for_user(db: Session, user_id) -> list[str]:
    user = db.get(User, user_id)
    profile = getattr(user, "profile", None) if user is not None else None
    stored = profile.interests if profile is not None else None
    if not isinstance(stored, list):
        return []
    return [item for item in stored if item in VOCABULARY]


def set_for_user(db: Session, user_id, values: list[str] | None) -> list[str]:
    user = db.get(User, user_id)
    if user is None or user.profile is None:
        raise LookupError("profile_missing")
    cleaned = normalize(values)
    user.profile.interests = cleaned
    db.flush()
    return cleaned


def practice_wrapper(db: Session, user_id) -> str | None:
    return scenario(for_user(db, user_id))


def counts(db: Session) -> dict[str, int]:
    """How many learners picked each interest; the operator sees demand, not identities."""
    from app.db.models import Profile

    result = {key: 0 for key in VOCABULARY}
    for stored in db.scalars(select(Profile.interests)):
        if isinstance(stored, list):
            for key in stored:
                if key in result:
                    result[key] += 1
    return result
