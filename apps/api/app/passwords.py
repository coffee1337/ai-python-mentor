"""Breached-password screening with the HIBP k-anonymity range API.

Only the first five hex characters of the SHA-1 hash leave the process; the
suffix never does, so the password itself is never transmitted. The check is
best effort by design: a network failure logs one line and lets registration
continue, because an outage of a third party must not lock every learner out.
Set PASSWORD_BREACH_CHECK=0 to disable it explicitly.
"""
from __future__ import annotations

import hashlib
import logging
import os

import httpx

logger = logging.getLogger("mentor.security")

RANGE_URL = "https://api.pwnedpasswords.com/range/"
MAX_BODY_BYTES = 512 * 1024


def enabled() -> bool:
    setting = os.getenv("PASSWORD_BREACH_CHECK", "").strip().lower()
    if setting in {"0", "false", "no"}:
        return False
    if setting in {"1", "true", "yes"}:
        return True
    # Default on only outside development so tests never depend on the network.
    return os.getenv("APP_ENV", "development").casefold() == "production"


def _timeout() -> float:
    try:
        value = float(os.getenv("PASSWORD_BREACH_TIMEOUT_SECONDS", "3"))
    except ValueError:
        return 3.0
    return min(max(value, 0.5), 10.0)


def breach_count(password: str, *, transport: httpx.BaseTransport | None = None) -> int | None:
    """Return how many breaches contain this password, or None when unknown."""
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        with httpx.Client(timeout=_timeout(), follow_redirects=False, trust_env=False,
                          transport=transport) as client:
            response = client.get(RANGE_URL + prefix, headers={"Add-Padding": "true",
                                                              "User-Agent": "ai-python-mentor"})
            if response.status_code != 200:
                raise ValueError("range lookup failed")
            body = response.content
            if len(body) > MAX_BODY_BYTES:
                raise ValueError("range response too large")
    except (httpx.HTTPError, ValueError, UnicodeError) as exc:
        logger.info('{"event": "password_breach_check_failed", "reason": "%s"}', type(exc).__name__)
        return None
    for line in body.decode("ascii", "ignore").splitlines():
        candidate, _, count = line.partition(":")
        if candidate.strip().upper() == suffix:
            try:
                return int(count.strip() or 0)
            except ValueError:
                return 0
    return 0


def is_breached(password: str, *, transport: httpx.BaseTransport | None = None) -> bool:
    """True when the password appears in a known breach and checking is on."""
    if not enabled():
        return False
    count = breach_count(password, transport=transport)
    return bool(count and count > 0)
