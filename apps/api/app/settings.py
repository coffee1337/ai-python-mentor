"""Environment-backed settings for private service integrations."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


class SettingsError(ValueError):
    """A required server-side setting is absent or invalid."""


@dataclass(frozen=True)
class RunnerSettings:
    url: str
    auth_token: str
    timeout_seconds: float


def load_runner_settings() -> RunnerSettings:
    url = os.getenv("RUNNER_URL", "").strip()
    auth_token = os.getenv("RUNNER_AUTH_TOKEN", "").strip()
    raw_timeout = os.getenv("RUNNER_REQUEST_TIMEOUT_SECONDS", "12").strip()
    try:
        parsed = urlsplit(url)
        timeout = float(raw_timeout)
    except (TypeError, ValueError):
        raise SettingsError("Runner settings are invalid") from None
    try:
        port_is_valid = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        port_is_valid = False
    valid_url = (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and port_is_valid
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )
    valid_token = 1 <= len(auth_token) <= 4096 and all(33 <= ord(char) <= 126 for char in auth_token)
    if not url or not valid_token or not valid_url or not 1 <= timeout <= 60:
        raise SettingsError("Runner settings are invalid")
    return RunnerSettings(url=url, auth_token=auth_token, timeout_seconds=timeout)
