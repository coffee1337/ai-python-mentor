"""Private HTTP client for the security-reviewed Python Runner worker.

The API process deliberately never executes learner source.  This module only
speaks the versioned private wire contract and fails closed when the worker
cannot provide a trustworthy response.
"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError, field_validator

from app.settings import RunnerSettings, SettingsError, load_runner_settings

PROTOCOL_VERSION = 1
RUNNER_ENDPOINT_PATH = "/internal/v1/runner/executions"
MAX_RESPONSE_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 16 * 1024
MAX_ERROR_TEXT_BYTES = 4096
MAX_TESTS = 10_000
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_ATTEMPT_CONTEXT: ContextVar[tuple[int, str] | None] = ContextVar("runner_attempt_context", default=None)


@dataclass(frozen=True)
class RunnerConfig:
    url: str
    auth_token: str
    timeout: float


@dataclass(frozen=True)
class RunnerResult:
    status: str
    message: str
    exit_code: int | None = None
    tests_passed: int = 0
    tests_total: int = 0
    timeout: bool = False
    resource_violation: bool = False
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    error_code: str | None = None


class RunnerUnavailable(RuntimeError):
    """The worker was not configured or did not provide a trustworthy result."""


class RunnerError(RuntimeError):
    """A locally detected request/contract error before a result is available."""


class _RunnerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: StrictInt = PROTOCOL_VERSION
    exercise_id: StrictStr = Field(min_length=1, max_length=80)
    exercise_version: StrictInt = Field(ge=1)
    language: Literal["python"]
    source: StrictStr = Field(min_length=1, max_length=20000)
    mode: Literal["function"]

    @field_validator("source")
    @classmethod
    def source_is_bounded_in_utf8(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 80 * 1024:
            raise ValueError("source exceeds the UTF-8 byte limit")
        return value


_WireStatus = Literal[
    "finished",
    "timeout",
    "resource_violation",
    "error",
    "unavailable",
    "in_progress",
]


class _RunnerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: StrictInt
    idempotency_key: StrictStr = Field(min_length=1, max_length=128)
    status: _WireStatus
    tests_passed: StrictInt = Field(ge=0, le=MAX_TESTS)
    tests_total: StrictInt = Field(ge=0, le=MAX_TESTS)
    timeout: StrictBool
    resource_violation: StrictBool
    stdout: StrictStr
    stderr: StrictStr
    stdout_truncated: StrictBool
    stderr_truncated: StrictBool
    exit_code: StrictInt | None
    error_code: StrictStr | None
    message: StrictStr | None

    @field_validator("stdout", "stderr")
    @classmethod
    def output_is_bounded(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise ValueError("runner output exceeds the response limit")
        return value

    @field_validator("error_code", "message")
    @classmethod
    def error_text_is_bounded(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > MAX_ERROR_TEXT_BYTES:
            raise ValueError("runner error text exceeds the response limit")
        return value


class _RunnerErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: StrictStr = Field(min_length=1, max_length=128)
    message: StrictStr = Field(min_length=1, max_length=MAX_ERROR_TEXT_BYTES)

    @field_validator("message")
    @classmethod
    def message_is_bounded_in_utf8(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_ERROR_TEXT_BYTES:
            raise ValueError("runner error text exceeds the response limit")
        return value


def configuration() -> RunnerConfig:
    """Load runner settings without exposing credentials in errors or logs."""
    try:
        settings: RunnerSettings = load_runner_settings()
    except SettingsError as exc:
        raise RunnerUnavailable("Runner is not configured") from exc
    return RunnerConfig(
        url=_endpoint_url(settings.url),
        auth_token=settings.auth_token,
        timeout=settings.timeout_seconds,
    )


def _endpoint_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    if path == RUNNER_ENDPOINT_PATH:
        return url.rstrip("/")
    return url.rstrip("/") + RUNNER_ENDPOINT_PATH


def _bounded_body(response: httpx.Response) -> bytes:
    raw = bytearray()
    try:
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RunnerError("Runner response is too large")
    except UnicodeError as exc:
        raise RunnerError("Runner response is not valid UTF-8") from exc
    return bytes(raw)


def _validate_wire_response(response: _RunnerResponse, *, expected_key: str, http_status: int) -> None:
    if response.protocol_version != PROTOCOL_VERSION:
        raise RunnerError("Unsupported runner protocol version")
    if response.idempotency_key != expected_key:
        raise RunnerError("Runner idempotency key mismatch")
    if response.tests_passed > response.tests_total:
        raise RunnerError("Runner test counts are invalid")
    if response.status == "finished" and response.tests_total == 0:
        raise RunnerError("Runner finished without trustworthy test counts")
    if response.status in {"finished", "error", "unavailable", "in_progress"} and (
        response.timeout or response.resource_violation
    ):
        raise RunnerError("Runner status flags are invalid")
    if response.status == "timeout" and (not response.timeout or response.resource_violation):
        raise RunnerError("Runner timeout flags are invalid")
    if response.status == "resource_violation" and not response.resource_violation:
        raise RunnerError("Runner resource flags are invalid")
    if response.status == "in_progress" and (
        response.tests_passed != 0
        or response.tests_total != 0
        or response.stdout
        or response.stderr
        or response.exit_code is not None
    ):
        raise RunnerError("Runner in-progress response contains a partial result")
    if http_status == 202 and response.status != "in_progress":
        raise RunnerError("Runner returned an invalid 202 response")
    if http_status == 200 and response.status == "in_progress":
        raise RunnerError("Runner returned an invalid 200 response")
    if http_status == 503 and (
        response.status != "unavailable" or response.error_code != "worker_not_ready"
    ):
        raise RunnerError("Runner returned an invalid 503 response")


def _parse_response(raw: bytes, *, expected_key: str, http_status: int) -> _RunnerResponse:
    try:
        payload = json.loads(raw.decode("utf-8"))
        response = _RunnerResponse.model_validate(payload)
        _validate_wire_response(response, expected_key=expected_key, http_status=http_status)
        return response
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValidationError, RunnerError) as exc:
        raise RunnerError("Runner response failed contract validation") from exc


def _parse_error_response(raw: bytes) -> None:
    try:
        payload = json.loads(raw.decode("utf-8"))
        _RunnerErrorResponse.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise RunnerError("Runner error response failed contract validation") from exc


def _message(response: _RunnerResponse, status: str) -> str:
    # Do not echo worker-controlled prose into the learner-facing API response.
    if status in {"passed", "failed"}:
        return f"{response.tests_passed}/{response.tests_total} tests passed"
    return {
        "timeout": "Runner timed out",
        "resource_violation": "Runner resource limit exceeded",
        "error": "Runner failed",
    }.get(status, "Runner is unavailable")


class Runner:
    def __init__(self, *, transport: httpx.BaseTransport | None = None):
        # Injectable only for focused transport tests; production uses httpx defaults.
        self._transport = transport

    @contextmanager
    def attempt_context(self, *, exercise_version: int, idempotency_key: str):
        token = _ATTEMPT_CONTEXT.set((exercise_version, idempotency_key))
        try:
            yield
        finally:
            _ATTEMPT_CONTEXT.reset(token)

    def run(
        self,
        *,
        exercise_id: str,
        exercise_version: int | None = None,
        source_code: str,
        language: str,
        mode: str,
        idempotency_key: str | None = None,
    ) -> RunnerResult:
        """Submit source to the private worker; never execute source locally."""
        if exercise_version is None or idempotency_key is None:
            context = _ATTEMPT_CONTEXT.get()
            if context is not None:
                exercise_version, idempotency_key = context
        if exercise_version is None or idempotency_key is None:
            raise RunnerUnavailable("Runner requires a pinned exercise version and idempotency key")
        if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise RunnerError("Runner idempotency key is invalid")
        try:
            request = _RunnerRequest(
                exercise_id=exercise_id,
                exercise_version=exercise_version,
                language=language,
                source=source_code,
                mode=mode,
            )
            config = configuration()
        except (ValidationError, RunnerUnavailable) as exc:
            if isinstance(exc, RunnerUnavailable):
                raise
            raise RunnerError("Runner request failed contract validation") from exc

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {config.auth_token}",
            "Idempotency-Key": idempotency_key,
        }
        try:
            with httpx.Client(
                timeout=config.timeout,
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                with client.stream("POST", config.url, headers=headers, json=request.model_dump()) as response:
                    raw = _bounded_body(response)
                    if response.status_code in (200, 202):
                        wire = _parse_response(raw, expected_key=idempotency_key, http_status=response.status_code)
                    elif response.status_code == 503:
                        wire = _parse_response(raw, expected_key=idempotency_key, http_status=response.status_code)
                        if wire.status != "unavailable":
                            raise RunnerError("Runner returned an invalid 503 response")
                    elif response.status_code in (400, 401, 403, 409, 422, 429, 500):
                        _parse_error_response(raw)
                        raise RunnerUnavailable("Runner did not accept the execution")
                    else:
                        raise RunnerError("Runner returned an unsupported HTTP status")
        except RunnerUnavailable:
            raise
        except (RunnerError, httpx.HTTPError, OSError, ValueError, UnicodeError) as exc:
            raise RunnerUnavailable("Runner is temporarily unavailable") from exc

        status = wire.status
        if status == "finished":
            api_status = "passed" if wire.tests_total > 0 and wire.tests_passed == wire.tests_total else "failed"
        elif status in {"unavailable", "in_progress"}:
            api_status = "unavailable"
        else:
            api_status = status
        return RunnerResult(
            status=api_status,
            message=_message(wire, api_status),
            exit_code=wire.exit_code,
            tests_passed=wire.tests_passed,
            tests_total=wire.tests_total,
            timeout=wire.timeout,
            resource_violation=wire.resource_violation,
            stdout=wire.stdout,
            stderr=wire.stderr,
            stdout_truncated=wire.stdout_truncated,
            stderr_truncated=wire.stderr_truncated,
            error_code=wire.error_code,
        )


runner = Runner()
