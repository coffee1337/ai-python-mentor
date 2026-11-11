"""Quiet-hours window parsing, shared by the bot and the delivery outbox.

Kept dependency-free so the dispatcher can use it without importing the bot.
"""
from datetime import UTC, datetime

QUIET_FORMAT = "%H:%M"


def parse_quiet(value: str | None) -> tuple[object, object] | None:
    if not value:
        return None
    try:
        start_raw, end_raw = value.split("-", 1)
        return datetime.strptime(start_raw.strip(), QUIET_FORMAT).time(), datetime.strptime(end_raw.strip(), QUIET_FORMAT).time()
    except ValueError:
        return None


def in_quiet_hours(value: str | None, *, now: datetime | None = None) -> bool:
    """True while delivery to this chat should be postponed."""
    window = parse_quiet(value)
    if window is None:
        return False
    start, end = window
    current = (now or datetime.now(UTC)).time()
    if start <= end:
        return start <= current < end
    return current >= start or current < end
