"""Server-only Chat Completions adapter with explicit routing and bounded retries.

The domain knows only this module.  A task name selects a tier from the routing
catalog, the tier is an ordered chain of models, and each model gets a bounded
number of attempts with exponential backoff.  Provider error bodies never reach
callers, prompts and keys never reach logs, and every call reports the tokens it
actually billed.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field, ValidationError

from app import model_catalog

logger = logging.getLogger("ai.usage")

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_RESPONSE_BYTES = 65536
ATTEMPTS_PER_MODEL = 2


class GatewayError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


class ProviderMessage(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=12000)


class Choice(BaseModel):
    message: ProviderMessage
    finish_reason: str


class ProviderResponse(BaseModel):
    choices: list[Choice] = Field(min_length=1, max_length=1)
    usage: dict | None = None


@dataclass(frozen=True)
class GatewayConfig:
    url: str
    models: tuple[str, ...]
    key: str
    timeout: float
    task: str | None = None

    @property
    def model(self) -> str:
        return self.models[0]


def _timeout() -> float:
    try:
        value = float(os.getenv("AI_GATEWAY_TIMEOUT_SECONDS", "20"))
    except ValueError:
        raise GatewayError(503, "AI mentor is not configured") from None
    if not 1 <= value <= 60:
        raise GatewayError(503, "AI mentor is not configured")
    return value


def configuration(*, model_override: str | None = None, task: str | None = None) -> GatewayConfig:
    url = os.getenv("AI_GATEWAY_URL", "").strip()
    key = os.getenv("AI_GATEWAY_API_KEY", "").strip()
    try:
        parts = urlsplit(url)
        timeout = _timeout()
        if model_override:
            models = (model_override.strip(),)
            task = None
        elif os.getenv("AI_GATEWAY_MODEL", "").strip():
            # Explicit pin wins: an operator can freeze one model without
            # editing the catalog (rollback path during an incident).
            models, task = (os.getenv("AI_GATEWAY_MODEL", "").strip(),), None
        else:
            try:
                catalog = model_catalog.load()
                models = catalog.chain(task)
                task = task or catalog.default_task
            except model_catalog.RoutingError:
                raise GatewayError(503, "AI mentor is not configured") from None
        valid = (parts.scheme == "https" and parts.hostname and not parts.username
                 and not parts.password and not parts.query and not parts.fragment
                 and all(models) and key)
    except ValueError:
        valid = False
    if not valid:
        raise GatewayError(503, "AI mentor is not configured")
    return GatewayConfig(url, models, key, timeout, task)


def _retry_delay(attempt: int) -> float:
    try:
        base = float(os.getenv("AI_RETRY_BASE_SECONDS", "0.4"))
    except ValueError:
        base = 0.4
    base = min(max(base, 0.0), 5.0)
    return min(base * (2 ** attempt), 4.0) * (1 + random.random() * 0.25)


def _total_budget() -> float:
    try:
        value = float(os.getenv("AI_GATEWAY_TOTAL_BUDGET_SECONDS", "45"))
    except ValueError:
        return 45.0
    return min(max(value, 5.0), 120.0)


def _call_once(config: GatewayConfig, model: str, messages: list[dict[str, str]],
               budget: int, timeout: float) -> tuple[str, dict | None]:
    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        with client.stream(
            "POST", config.url,
            headers={"Authorization": f"Bearer {config.key}"},
            json={"model": model, "messages": messages, "max_completion_tokens": budget},
        ) as response:
            if response.status_code in RETRY_STATUS:
                raise httpx.HTTPStatusError("retryable", request=response.request, response=response)
            response.raise_for_status()
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError("Response too large")
    parsed = ProviderResponse.model_validate(json.loads(raw))
    choice = parsed.choices[0]
    if choice.message.role != "assistant" or choice.finish_reason != "stop" or not choice.message.content.strip():
        raise ValueError("Incomplete response")
    return choice.message.content.strip(), parsed.usage


def _report(task: str | None, model: str, usage: dict | None, attempts: int,
            latency_ms: int, status: str) -> dict[str, Any]:
    prompt = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    completion = usage.get("completion_tokens") if isinstance(usage, dict) else None
    prompt = prompt if type(prompt) is int and prompt >= 0 else None
    completion = completion if type(completion) is int and completion >= 0 else None
    try:
        price = model_catalog.load().price(model)
    except model_catalog.RoutingError:
        price = None
    micro = (price.micro_usd(prompt or 0, completion or 0)
             if price and prompt is not None and completion is not None else None)
    logger.info(json.dumps({"event": "ai_call", "task": task, "model": model, "status": status,
                            "attempts": attempts, "prompt_tokens": prompt,
                            "completion_tokens": completion, "micro_usd": micro,
                            "latency_ms": latency_ms}, sort_keys=True))
    enriched = dict(usage or {})
    enriched.update({"model": model, "attempts": attempts, "latency_ms": latency_ms})
    if micro is not None:
        enriched["micro_usd"] = micro
    return enriched


def warmup() -> bool:
    """One tiny call at startup so the first learner does not pay a cold start.

    Provider-side cold starts were measured at ~40 s for the first request after
    a pause; later requests to the same model answer in 4-10 s. Warmup is
    best-effort: a failure is logged and never blocks startup.
    """
    if os.getenv("AI_WARMUP_ENABLED", "1").strip() == "0":
        return False
    try:
        config = configuration(task="tutor_chat")
        generate_with_usage(config, [{"role": "user", "content": "ping"}], max_completion_tokens=8)
        return True
    except GatewayError as exc:
        logger.info(json.dumps({"event": "ai_warmup_failed", "status": exc.status}))
        return False


def generate(config: GatewayConfig, messages: list[dict[str, str]]) -> str:
    content, _ = generate_with_usage(config, messages)
    return content


def generate_with_usage(
    config: GatewayConfig,
    messages: list[dict[str, str]],
    *,
    max_completion_tokens: int = 2200,
) -> tuple[str, dict | None]:
    """Walk the tier chain; every model gets a bounded number of attempts.

    Returns the answer plus usage enriched with the answering model, the attempt
    count and the cost in micro-USD when the model is priced.  Raises 504 when
    the last failure was a timeout and 502 otherwise.
    """
    if not 1 <= max_completion_tokens <= 3000:
        raise ValueError("Invalid completion-token budget")
    started = time.monotonic()
    deadline = started + _total_budget()
    attempts = 0
    last_error: Exception | None = None
    last_status = 502
    for model in config.models:
        for attempt in range(ATTEMPTS_PER_MODEL):
            remaining = deadline - time.monotonic()
            if remaining <= 1:
                break
            attempts += 1
            try:
                content, usage = _call_once(config, model, messages, max_completion_tokens,
                                            min(config.timeout, remaining))
                return content, _report(config.task, model, usage, attempts,
                                        int((time.monotonic() - started) * 1000), "ok")
            except httpx.TimeoutException as exc:
                last_error, last_status = exc, 504
            except httpx.HTTPStatusError as exc:
                last_error, last_status = exc, 502
                if exc.response.status_code not in RETRY_STATUS:
                    break
            except httpx.HTTPError as exc:
                last_error, last_status = exc, 502
            except (ValidationError, ValueError, UnicodeError) as exc:
                # A malformed envelope is not retried on the same model.
                last_error, last_status = exc, 502
                break
            if attempt + 1 < ATTEMPTS_PER_MODEL:
                time.sleep(_retry_delay(attempt))
        logger.info(json.dumps({"event": "ai_call_failed", "task": config.task, "model": model,
                                "status": last_status, "attempts": attempts,
                                "error": type(last_error).__name__ if last_error else None},
                               sort_keys=True))
    raise GatewayError(last_status if last_status == 504 else 502,
                       "AI mentor timed out; retry later" if last_status == 504
                       else "AI mentor is temporarily unavailable")
