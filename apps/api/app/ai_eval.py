"""Benchmark of the tutor on a fixed case set: correctness, usefulness, leakage, cost.

Every case is a real learner question with an expectation the product can check
mechanically: the answer must be in Russian, must not leak the graded answer, must
stay bounded, must invite the learner's own reasoning, and must not claim it ran code.
The run is stored, so a prompt or model change is comparable instead of remembered.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AIEvalRun

CASES_PATH = Path(__file__).resolve().parent.parent / "config" / "eval-cases.json"
CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
HALLUCINATION = re.compile(
    r"(я\s+(запустил|выполнил|проверил)|тесты?\s+прошл|код\s+выполнен|output:|вывод\s+программы)",
    re.IGNORECASE,
)
CLAIM_MASTERY = re.compile(r"(вы\s+(освоили|овладели)|навык\s+подтверждён|mastery)", re.IGNORECASE)


def load_cases(path: Path | None = None) -> list[dict]:
    path = path or CASES_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("Eval cases are missing")
    return cases


def score_answer(answer: str, case: dict) -> dict:
    """0–2 per dimension, no model in the loop: the rules are mechanical."""
    text = answer or ""
    russian = 1 if len(CYRILLIC.findall(text)) >= 40 else 0
    leaked = [needle for needle in case.get("forbidden", []) if needle and needle.casefold() in text.casefold()]
    leakage = 0 if leaked else 1
    bounded = 0 if len(text) > int(case.get("max_chars", 1200)) else 1
    invites = 1 if ("?" in text or case.get("invites_optional")) else 0
    honest = 0 if (HALLUCINATION.search(text) or CLAIM_MASTERY.search(text)) else 1
    points = [russian, leakage, bounded, invites, honest]
    return {
        "score": round(sum(points) / (2 * len(points)) * 2, 3),  # 0..2
        "dimensions": {
            "russian": russian,
            "no_leakage": leakage,
            "bounded": bounded,
            "invites_reasoning": invites,
            "no_false_claims": honest,
        },
        "leaked": leaked,
    }


def run(db: Session, *, config, cases: list[dict] | None = None, generate=None) -> AIEvalRun:
    """Execute the case set through the gateway and store the aggregate."""
    from app import ai_gateway, mentor_prompts, prompt_variants
    from app.exercise_snapshots import authored_snapshot

    cases = cases or load_cases()
    generate = generate or ai_gateway.generate
    version = prompt_variants.for_user("tutor_chat", None)
    results = []
    latencies: list[int] = []
    for case in cases:
        try:
            snapshot = authored_snapshot(case["lesson"])
        except ValueError:
            continue
        messages = mentor_prompts.context_messages(snapshot["lesson"], case.get("level"), case.get("mode", "teach"),
                                                   variant_instructions=prompt_variants.instructions("tutor_chat", version))
        messages.append({"role": "user", "content": case["question"]})
        started = datetime.now(UTC)
        try:
            answer = generate(config, messages)
        except Exception as error:  # provider failure is a failed case, not a crash
            results.append({"id": case["id"], "score": 0.0, "error": type(error).__name__})
            continue
        latencies.append(int((datetime.now(UTC) - started).total_seconds() * 1000))
        scored = score_answer(answer, case)
        results.append({"id": case["id"], **scored, "chars": len(answer)})

    scored_cases = [item for item in results if "dimensions" in item]
    total = len(scored_cases) or 1
    dimensions = {
        name: round(sum(item["dimensions"][name] for item in scored_cases) / total, 3)
        for name in ("russian", "no_leakage", "bounded", "invites_reasoning", "no_false_claims")
    }
    metrics = {
        "dimensions": dimensions,
        "average_score": round(sum(item["score"] for item in scored_cases) / total, 3),
        "cases": len(results),
        "failed_calls": sum(1 for item in results if "error" in item),
        "leakage_cases": [item["id"] for item in scored_cases if not item["dimensions"]["no_leakage"]],
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "avg_chars": round(sum(item["chars"] for item in scored_cases) / total) if scored_cases else None,
        "results": results,
    }
    row = AIEvalRun(
        id=uuid4(),
        model_id=config.model,
        prompt_version=version,
        cases=len(results),
        score=metrics["average_score"],
        metrics=metrics,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    return row


def history(db: Session, limit: int = 10) -> list[dict]:
    rows = db.scalars(select(AIEvalRun).order_by(AIEvalRun.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": str(row.id),
            "model": row.model_id,
            "prompt_version": row.prompt_version,
            "cases": row.cases,
            "score": row.score,
            "metrics": {key: value for key, value in (row.metrics or {}).items() if key != "results"},
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def report_path() -> Path:
    return Path(os.getenv("AI_EVAL_REPORT", str(CASES_PATH.parent.parent.parent / "docs" / "eval" / "report.json")))
