"""Runtime model routing: task -> tier -> ordered model chain.

The catalog is a deployment artefact, not a secret: model slugs, their provider
multiplier and the price used for cost accounting.  Prices are micro-USD per
one million tokens; they are configuration because the provider bills in its own
units, and exact money must come from an explicit number rather than a guess.

Failure to load or validate the file is a configuration error, never a fallback
to a hardcoded model: routing changes must be visible in a diff.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "model-routing.json"

# Task keys used by the application. They are stable identifiers, so a routing
# change never requires a code change.
TASKS = (
    "tutor_chat",
    "hint_ladder",
    "error_explanation",
    "answer_feedback",
    "lesson_generation",
    "practice_generation",
    "code_review",
    "plan_generation",
)


class RoutingError(ValueError):
    """The routing file is missing, unreadable or inconsistent."""


@dataclass(frozen=True)
class ModelPrice:
    input_micro_usd_per_million: int
    output_micro_usd_per_million: int
    multiplier: float

    def micro_usd(self, prompt_tokens: int, completion_tokens: int) -> int:
        return (prompt_tokens * self.input_micro_usd_per_million
                + completion_tokens * self.output_micro_usd_per_million + 999_999) // 1_000_000


@dataclass(frozen=True)
class Catalog:
    version: int
    models: dict[str, ModelPrice]
    tiers: dict[str, tuple[str, ...]]
    tasks: dict[str, str]
    default_task: str

    def chain(self, task: str | None) -> tuple[str, ...]:
        tier = self.tasks.get(task or self.default_task)
        if tier is None or tier not in self.tiers:
            raise RoutingError("unknown ai task")
        return self.tiers[tier]

    def price(self, model: str) -> ModelPrice | None:
        return self.models.get(model)


_cache: dict[str, tuple[float, Catalog]] = {}


def catalog_path() -> Path:
    return Path(os.getenv("AI_MODEL_ROUTING_FILE", "").strip() or DEFAULT_PATH)


def _positive_int(value, field: str) -> int:
    if type(value) is not int or not 0 <= value <= 100_000_000:
        raise RoutingError(f"invalid {field}")
    return value


def parse(document: dict) -> Catalog:
    if not isinstance(document, dict) or set(document) != {"version", "provider", "models", "tiers", "tasks", "default_task"}:
        raise RoutingError("invalid routing document")
    if document["version"] != 1:
        raise RoutingError("unsupported routing version")
    provider = document["provider"]
    if not isinstance(provider, dict) or set(provider) != {"name", "checked_at"} or not all(
            isinstance(provider[key], str) and provider[key].strip() for key in ("name", "checked_at")):
        raise RoutingError("invalid provider block")
    models: dict[str, ModelPrice] = {}
    for name, price in document["models"].items():
        if not isinstance(name, str) or not name.strip():
            raise RoutingError("invalid model id")
        if not isinstance(price, dict) or set(price) != {"input_micro_usd_per_million",
                                                         "output_micro_usd_per_million", "multiplier"}:
            raise RoutingError("invalid model price")
        if type(price["multiplier"]) not in (int, float) or not 0 < float(price["multiplier"]) <= 100:
            raise RoutingError("invalid model multiplier")
        models[name] = ModelPrice(
            _positive_int(price["input_micro_usd_per_million"], "input price"),
            _positive_int(price["output_micro_usd_per_million"], "output price"),
            float(price["multiplier"]),
        )
    tiers: dict[str, tuple[str, ...]] = {}
    for tier, entries in document["tiers"].items():
        if not isinstance(entries, list) or not 1 <= len(entries) <= 4:
            raise RoutingError("invalid tier")
        for model in entries:
            if model not in models:
                raise RoutingError("tier references an unpriced model")
        tiers[tier] = tuple(entries)
    tasks = document["tasks"]
    if not isinstance(tasks, dict) or set(tasks) != set(TASKS):
        raise RoutingError("routing must define exactly the known tasks")
    for tier in tasks.values():
        if tier not in tiers:
            raise RoutingError("task references an unknown tier")
    default_task = document["default_task"]
    if default_task not in tasks:
        raise RoutingError("invalid default task")
    return Catalog(document["version"], models, tiers, tasks, default_task)


def load(path: Path | None = None) -> Catalog:
    path = Path(path) if path is not None else catalog_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        raise RoutingError("routing file is missing") from None
    cached = _cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise RoutingError("routing file is unreadable") from None
    catalog = parse(document)
    _cache[str(path)] = (mtime, catalog)
    return catalog
