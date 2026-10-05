"""Environment-backed settings for private service integrations."""
from __future__ import annotations

import os
import json
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlsplit


class SettingsError(ValueError):
    """A required server-side setting is absent or invalid."""


@dataclass(frozen=True)
class RunnerSettings:
    url: str
    auth_token: str
    timeout_seconds: float
    ca_file: str | None = None
    client_cert_file: str | None = None
    client_key_file: str | None = None


def load_runner_settings(*, allow_test_transport: bool = False) -> RunnerSettings:
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
    files = [os.getenv(name, "").strip() for name in (
        "RUNNER_CA_FILE", "RUNNER_CLIENT_CERT_FILE", "RUNNER_CLIENT_KEY_FILE",
    )]
    if not allow_test_transport:
        try:
            policy_file = Path(os.environ["RUNNER_VERIFIED_POLICY_FILE"])
            if policy_file.stat().st_size > 4096:
                raise ValueError()
            policy = json.loads(policy_file.read_text())
            reviewed = policy.get("policy") == "python-authored-v1" and policy.get("isolation_verified") is True
            if parsed.scheme != "https" or not reviewed or not all(Path(p).is_file() for p in files):
                raise ValueError()
        except (KeyError, OSError, ValueError, TypeError):
            raise SettingsError("Runner mutual authentication and verified isolation are required") from None
    return RunnerSettings(url=url, auth_token=auth_token, timeout_seconds=timeout,
                          ca_file=files[0] or None, client_cert_file=files[1] or None,
                          client_key_file=files[2] or None)
