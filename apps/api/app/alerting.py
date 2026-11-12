"""Operator alerts: a message in the owner's chat, not a line in a file.

Alerting is best effort by design: a missing chat id or an unreachable Bot API must
never break a learner request, so every send is fire-and-forget and logged by outcome
only. The text carries numbers, never user content.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("alerts")

_last_sent: dict[str, float] = {}
MIN_INTERVAL_SECONDS = 3600


def owner_chat() -> str | None:
    chat = os.getenv("TELEGRAM_ALERT_CHAT_ID", "").strip()
    return chat if chat.lstrip("-").isdigit() and len(chat) <= 32 else None


def send(text: str, *, key: str = "generic") -> bool:
    """Send to the owner's chat at most once per key per hour."""
    chat = owner_chat()
    if chat is None:
        return False
    now = time.monotonic()
    last = _last_sent.get(key)
    if last is not None and now - last < MIN_INTERVAL_SECONDS:
        return False
    from app.telegram_bot import bot_token, send_message

    if bot_token() is None:
        return False
    delivered = send_message(chat, text[:3500])
    if delivered:
        _last_sent[key] = now
        logger.info("alert_sent key=%s", key)
    else:
        logger.warning("alert_failed key=%s", key)
    return delivered


def spend_alert(day: str, spent_micro_usd: int, limit_micro_usd: int) -> bool:
    """Daily AI budget guard: one message per day when 80% of the budget is spent."""
    percent = round(spent_micro_usd / limit_micro_usd * 100) if limit_micro_usd else 0
    text = (
        f"AI-бюджет: израсходовано {percent}% дневного лимита.\n"
        f"Потрачено ${spent_micro_usd / 1_000_000:.2f} из ${limit_micro_usd / 1_000_000:.2f} за {day} (UTC).\n"
        "Проверьте расход: /admin/analytics и правило AiSpendHigh."
    )
    return send(text, key=f"spend:{day}")


def reset_for_tests() -> None:
    _last_sent.clear()
