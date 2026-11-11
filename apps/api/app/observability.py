"""Optional error reporting. Disabled unless SENTRY_DSN is configured.

Events are scrubbed before they leave the process: request bodies, headers,
cookies and query strings never reach the error tracker, because a learner's
source code and a session token can both live there.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("mentor.observability")
_SENSITIVE_HEADERS = ("authorization", "cookie", "set-cookie", "x-csrf-token")


def _scrub(event: dict, hint: dict) -> dict | None:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("query_string", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for name in list(headers):
                if name.lower() in _SENSITIVE_HEADERS:
                    headers[name] = "[redacted]"
    event.pop("user", None)
    return event


def init_sentry() -> bool:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:  # pragma: no cover - dependency is optional at runtime
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return False
    try:
        rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0"))
    except ValueError:
        rate = 0.0
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("APP_ENV", "production"),
        release=os.getenv("RELEASE_VERSION") or None,
        traces_sample_rate=min(max(rate, 0.0), 1.0),
        send_default_pii=False,
        before_send=_scrub,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    logger.info("sentry enabled")
    return True
