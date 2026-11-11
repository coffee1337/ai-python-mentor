"""Prometheus metrics for latency, errors, AI spend, quotas and the job queue.

Only counters, histograms and gauges with bounded label sets: no user ids, no
lesson ids, no prompts. Route labels use the FastAPI route template, so an
attacker cannot create new series by inventing URLs.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

REQUEST_DURATION = Histogram(
    "apm_http_request_duration_seconds",
    "HTTP request latency",
    ("method", "route", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
REQUESTS = Counter(
    "apm_http_requests_total",
    "HTTP requests by outcome",
    ("method", "route", "status"),
)
AI_CALLS = Counter(
    "apm_ai_calls_total",
    "AI gateway calls by task, model and outcome",
    ("task", "model", "status"),
)
AI_TOKENS = Counter(
    "apm_ai_tokens_total",
    "Provider tokens by direction",
    ("model", "direction"),
)
AI_SPEND = Counter(
    "apm_ai_spend_micro_usd_total",
    "AI spend in micro-USD by task and model",
    ("task", "model"),
)
QUOTA_REJECTIONS = Counter(
    "apm_quota_rejections_total",
    "AI admissions rejected by reason",
    ("reason",),
)
EXECUTIONS = Counter(
    "apm_runner_executions_total",
    "Learner code executions by status",
    ("status",),
)
QUEUE_DEPTH = Gauge(
    "apm_execution_queue_depth",
    "Durable execution jobs waiting for the runner",
)
DB_UP = Gauge("apm_db_up", "1 when the database answers a probe")


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    labels = (method, route, str(status))
    REQUEST_DURATION.labels(*labels).observe(seconds)
    REQUESTS.labels(*labels).inc()


def observe_ai(task: str | None, model: str | None, status: str, usage: dict | None = None) -> None:
    AI_CALLS.labels(task or "none", model or "none", status).inc()
    if not isinstance(usage, dict):
        return
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    micro = usage.get("micro_usd")
    if type(prompt) is int and prompt >= 0:
        AI_TOKENS.labels(model or "none", "input").inc(prompt)
    if type(completion) is int and completion >= 0:
        AI_TOKENS.labels(model or "none", "output").inc(completion)
    if type(micro) is int and micro >= 0:
        AI_SPEND.labels(task or "none", model or "none").inc(micro)


def observe_execution(status: str) -> None:
    EXECUTIONS.labels(status).inc()


def observe_quota(reason: str) -> None:
    QUOTA_REJECTIONS.labels(reason).inc()


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


@contextmanager
def timer():
    started = time.monotonic()
    try:
        yield lambda: time.monotonic() - started
    finally:
        pass
