"""Live smoke test for the AI gateway: routing, Russian and English answers, cost.

Run against the real provider; nothing here is mocked.

    cd apps/api && PYTHONPATH=. python ../../scripts/ai-smoke.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import httpx  # noqa: E402

from app import ai_gateway, model_catalog  # noqa: E402


def load_env() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def provider_models() -> set[str]:
    url = model_catalog.load() and os.environ["AI_GATEWAY_URL"].rsplit("/chat/completions", 1)[0] + "/models"
    response = httpx.get(url, headers={"Authorization": f"Bearer {os.environ['AI_GATEWAY_API_KEY']}"}, timeout=30)
    response.raise_for_status()
    return {row["id"] for row in response.json()["data"]}


def main() -> int:
    load_env()
    catalog = model_catalog.load()
    available = provider_models()
    missing = sorted({model for chain in catalog.tiers.values() for model in chain} - available)
    print(f"routing models present at provider: {len(available)} total, missing={missing or 'none'}")

    prompts = {
        "ru": "Объясни в двух предложениях, зачем нужен оператор return в функции Python.",
        "en": "Explain in two sentences why the return statement matters in a Python function.",
    }
    failures = 0
    for task in ("tutor_chat", "lesson_generation"):
        config = ai_gateway.configuration(task=task)
        for language, prompt in prompts.items():
            try:
                content, usage = ai_gateway.generate_with_usage(
                    config, [{"role": "user", "content": prompt}], max_completion_tokens=300)
            except ai_gateway.GatewayError as exc:
                failures += 1
                print(f"FAIL task={task} lang={language} status={exc.status} detail={exc.detail}")
                continue
            micro = usage.get("micro_usd")
            usd = f"${micro / 1_000_000:.6f}" if isinstance(micro, int) else "unknown"
            print(f"ok task={task} lang={language} model={usage['model']} "
                  f"prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')} "
                  f"cost={usd} attempts={usage['attempts']} latency={usage['latency_ms']}ms")
            print(f"   ответ: {content[:160].replace(chr(10), ' ')}")

    balance = httpx.get(os.environ["AI_GATEWAY_URL"].rsplit("/v1/", 1)[0] + "/v1/balance",
                        headers={"Authorization": f"Bearer {os.environ['AI_GATEWAY_API_KEY']}"}, timeout=30)
    if balance.status_code == 200:
        print("provider token balance:", balance.json().get("token_balance"))
    print("RESULT:", "ok" if failures == 0 and not missing else "failed")
    return 0 if failures == 0 and not missing else 1


if __name__ == "__main__":
    sys.exit(main())
