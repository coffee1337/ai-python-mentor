"""Telegram channel: webhook, account binding and learning commands.

The bot is a full learning surface, not a notification pipe: it answers /today,
/progress, /quiz, /streak and /settings, and a quiz answer lands in the same
evidence store as the web check with a `telegram` source marker.

Safety rules encoded here:
  * the token and the webhook secret come only from the environment;
  * the webhook path carries a secret and the header must match it;
  * every update_id is stored once, so a repeated delivery never re-applies;
  * a chat sees only the account it is bound to, and only while the binding is live.
"""

from __future__ import annotations

import contextlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.account_services import consume_token, throttle, utcnow
from app.db.account_models import NotificationOutbox, TelegramBinding, TelegramUpdate
from app.db.models import (
    ExerciseVersion,
    KnowledgeCheckAttempt,
    KnowledgeCheckResponse,
    LessonCompletion,
    User,
)
from app.db.session import get_db
from app.exercise_snapshots import authored_snapshot
from app.learning import learning_path
from app.mailer import base_url
from app.quiet_hours import in_quiet_hours
from app.skill_evidence import record_evidence

logger = logging.getLogger("telegram")
router = APIRouter(prefix="/telegram", tags=["telegram"])

CALLBACK_BYTES = 64
MESSAGE_LIMIT = 4096
QUIET_FORMAT = "%H:%M"


def bot_token() -> str | None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if 16 <= len(token) <= 200 and all(char.isalnum() or char in "_:-" for char in token):
        return token
    return None


def webhook_secret() -> str | None:
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    return secret if len(secret) >= 32 and secret.isascii() else None


def api_base() -> str:
    """Telegram API origin; tests point this at a local mock server."""
    return os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")


def configured() -> bool:
    return bot_token() is not None and webhook_secret() is not None


def _call(method: str, payload: dict, *, timeout: float = 10.0) -> dict | None:
    """Call the Bot API without letting the token reach logs or exceptions."""
    token = bot_token()
    if token is None:
        return None
    request = urllib.request.Request(
        f"{api_base()}/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return json.loads(response.read(2_000_000).decode("utf-8"))
    except urllib.error.HTTPError as error:
        # 429 and 5xx are transient for the caller; the body is never logged raw.
        logger.warning("telegram_call_failed method=%s status=%s", method, error.code)
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        logger.warning("telegram_call_failed method=%s error=%s", method, type(error).__name__)
    return None


def send_message(chat_id: str, text: str, *, keyboard: list[list[dict]] | None = None) -> bool:
    payload: dict = {"chat_id": chat_id, "text": text[:MESSAGE_LIMIT], "disable_web_page_preview": True}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return _call("sendMessage", payload) is not None


def answer_callback(callback_id: str, text: str = "") -> None:
    _call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:200]})


def edit_message(chat_id: str, message_id: int, text: str) -> None:
    _call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text[:MESSAGE_LIMIT]})


def link_url(raw_token: str) -> str | None:
    username = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    return f"https://t.me/{username}?start={raw_token}" if username else None


# ---------------------------------------------------------------- binding state

def active_binding(db: Session, chat_id: str) -> TelegramBinding | None:
    binding = db.scalar(select(TelegramBinding).where(TelegramBinding.chat_id == chat_id))
    return binding if binding is not None and binding.revoked_at is None else None


def binding_for_user(db: Session, user_id: UUID) -> TelegramBinding | None:
    binding = db.get(TelegramBinding, user_id)
    return binding if binding is not None and binding.revoked_at is None else None


def revoke(db: Session, binding: TelegramBinding) -> None:
    """Keep the row for history, free the chat id and cancel queued messages."""
    binding.revoked_at = utcnow()
    binding.chat_id = f"revoked-{binding.chat_id}-{int(binding.revoked_at.timestamp())}"[:40]
    db.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.user_id == binding.user_id,
            NotificationOutbox.channel == "telegram",
            NotificationOutbox.status != "delivered",
        )
        .values(status="cancelled", payload={})
    )


def bind(db: Session, raw_code: str, chat_id: str, username: str | None) -> tuple[bool, str]:
    """Attach a chat to the account that minted the one-time code."""
    existing = db.scalar(select(TelegramBinding).where(TelegramBinding.chat_id == chat_id))
    if existing is not None and existing.revoked_at is None:
        return False, "Этот чат уже привязан к аккаунту."
    try:
        user = consume_token(db, raw_code, "telegram_bind")
    except Exception:
        db.rollback()
        return False, "Код недействителен или истёк. Создайте новый в кабинете."
    binding = db.get(TelegramBinding, user.id)
    if binding is None:
        binding = TelegramBinding(user_id=user.id, chat_id=chat_id, username=(username or None))
        db.add(binding)
    else:
        binding.chat_id, binding.username = chat_id, username or binding.username
        binding.revoked_at = None
        binding.notifications_enabled = True
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False, "Этот чат уже привязан к другому аккаунту."
    return True, "Готово: чат привязан к аккаунту."


# ---------------------------------------------------------------- rendering

def _progress_snapshot(db: Session, user: User) -> dict:
    path = learning_path(db, user)
    completed = path.completed
    next_id = path.resume_lesson_id or path.next_lesson_id
    lesson_title = _lesson_title(next_id) if next_id else None
    days = db.scalars(
        select(func.date(LessonCompletion.completed_at))
        .where(LessonCompletion.user_id == user.id)
        .group_by(func.date(LessonCompletion.completed_at))
        .order_by(func.date(LessonCompletion.completed_at).desc())
    ).all()
    streak, cursor = 0, datetime.now(UTC).date()
    for day in days:
        current = day if isinstance(day, datetime) else datetime.fromisoformat(str(day))
        if current.date() == cursor:
            streak += 1
            cursor -= timedelta(days=1)
        elif current.date() == cursor - timedelta(days=1) and streak == 0:
            streak += 1
            cursor = current.date() - timedelta(days=1)
        else:
            break
    return {"completed": completed, "total": path.total,
            "next_lesson_id": next_id, "next_lesson_title": lesson_title, "streak": streak}


def _lesson_title(lesson_id: str) -> str:
    try:
        return str(authored_snapshot(lesson_id)["lesson"]["title"])
    except (ValueError, KeyError, TypeError):
        return lesson_id


def _web_link(path: str) -> str:
    return f"{base_url()}{path}"


def render_progress(data: dict) -> str:
    total = f" из {data['total']}" if data.get("total") else ""
    lines = [
        f"Пройдено уроков: {data['completed']}{total}",
        f"Серия дней подряд: {data['streak']}",
    ]
    if data.get("next_lesson_title"):
        lines.append(f"Следующий шаг: {data['next_lesson_title']}")
        lines.append(_web_link(f"/learn/{data['next_lesson_id']}"))
    return "\n".join(lines)


def render_today(data: dict) -> str:
    if not data.get("next_lesson_id"):
        return "Курс пройден полностью. Можно повторить слабые темы в разделе «Повторение»."
    link = _web_link("/learn/" + data["next_lesson_id"])
    return f"Сегодня: {data['next_lesson_title']}\nПродолжить в вебе: {link}"


def settings_text(db: Session, user: User, binding: TelegramBinding) -> str:
    quiet = binding.quiet_hours or "не заданы"
    return (
        "Настройки канала Telegram\n"
        f"Уведомления: {'включены' if binding.notifications_enabled else 'выключены'}\n"
        f"Тихие часы (UTC): {quiet}\n\n"
        "Отправить /unlink — отвязать чат.\n"
        "Тихие часы задаются командой /quiet 22:00-08:00."
    )


# ---------------------------------------------------------------- quiz

def _questions(lesson_id: str) -> list[dict]:
    try:
        snapshot = authored_snapshot(lesson_id)
    except ValueError:
        return []
    return list(snapshot.get("checks") or [])


def quiz_keyboard(lesson_id: str, question: dict) -> list[list[dict]]:
    rows = []
    for index, choice in enumerate(question["choices"]):
        data = f"qz:{lesson_id}:{question['id']}:{index}"
        if len(data.encode()) > CALLBACK_BYTES:
            continue
        rows.append([{"text": choice[:60], "callback_data": data}])
    return rows


def grade(lesson_id: str, question_id: str, index: int) -> tuple[bool, dict] | None:
    for question in _questions(lesson_id):
        if question["id"] != question_id:
            continue
        try:
            choice = question["choices"][int(index)]
        except (IndexError, ValueError):
            return None
        return choice == question["answer"], question
    return None


def record_quiz_evidence(db: Session, user: User, lesson_id: str, question: dict, choice: str, correct: bool) -> bool:
    """Persist the answer as a real knowledge-check attempt, then record evidence.

    Evidence is only accepted from a stored graded artefact, so the bot writes the
    same attempt/response rows the web check writes; a Telegram answer is therefore
    traceable to a lesson version and a specific question.
    """
    snapshot = None
    with contextlib.suppress(ValueError, KeyError, TypeError):
        snapshot = authored_snapshot(lesson_id)
    if snapshot is None:
        return False
    skill_id = snapshot["lesson"]["skill_id"]
    version = db.scalar(
        select(ExerciseVersion)
        .where(ExerciseVersion.exercise_id == lesson_id)
        .order_by(ExerciseVersion.version.desc())
    )
    if version is None:
        # A fresh install may not have published this lesson yet; seed the same
        # immutable version the web check would create.
        from app.exercise_hints import _seed_exercise

        with contextlib.suppress(Exception):
            version = _seed_exercise(db, lesson_id)
    if version is None:
        return False
    attempt = KnowledgeCheckAttempt(
        user_id=user.id,
        exercise_version_id=version.id,
        lesson_id=lesson_id,
        skill_id=skill_id,
        score=1.0 if correct else 0.0,
        passed=correct,
        created_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    db.add(
        KnowledgeCheckResponse(
            attempt_id=attempt.id,
            question_id=question["id"],
            answer=choice[:200],
            is_correct=correct,
            explanation=str(question.get("explanation", ""))[:2000],
        )
    )
    db.flush()
    record_evidence(
        db,
        user_id=user.id,
        skill_id=skill_id,
        source_type="knowledge_check_attempt",
        source_id=str(attempt.id),
        result_score=1.0 if correct else 0.0,
        assisted=False,
        hint_count=0,
        occurred_at=attempt.created_at,
        metadata={"channel": "telegram", "lesson_id": lesson_id, "question_id": question["id"]},
    )
    db.commit()
    return True


# ---------------------------------------------------------------- commands

HELP = (
    "Что умею:\n"
    "/today — следующий учебный шаг\n"
    "/progress — прогресс и серия дней\n"
    "/quiz — быстрый вопрос по текущей теме\n"
    "/streak — серия дней подряд\n"
    "/settings — уведомления и тихие часы\n"
    "/link <код> — привязать чат\n"
    "/unlink — отвязать чат\n"
    "/help — эта подсказка"
)


def handle_command(db: Session, chat_id: str, text: str, username: str | None) -> None:
    parts = text.strip().split()
    command = parts[0].split("@", 1)[0].lower()
    argument = parts[1] if len(parts) > 1 else ""

    if command in {"/start", "/link"}:
        if not argument:
            send_message(
                chat_id,
                "Привет! Я «Наставник AI».\n\n"
                "Чтобы получать план и заниматься здесь, привяжите чат: откройте кабинет → "
                "«Telegram» → «Получить код», затем отправьте /link <код>.\n\n" + HELP,
            )
            return
        ok, message = bind(db, argument, chat_id, username)
        send_message(chat_id, message + ("" if ok else "\n\nОткрыть кабинет: " + _web_link("/settings")))
        return

    binding = active_binding(db, chat_id)
    if binding is None:
        send_message(chat_id, "Чат не привязан к аккаунту. Отправьте /link <код из кабинета>.")
        return
    user = db.get(User, binding.user_id)
    if user is None or not user.is_active:
        send_message(chat_id, "Аккаунт недоступен. Привяжите чат заново: /link <код>.")
        return

    if command == "/help":
        send_message(chat_id, HELP)
    elif command in {"/today", "/start"}:
        send_message(chat_id, render_today(_progress_snapshot(db, user)),
                     keyboard=[[{"text": "Открыть в вебе", "url": _web_link("/learn")}]])
    elif command in {"/progress", "/streak"}:
        send_message(chat_id, render_progress(_progress_snapshot(db, user)))
    elif command == "/quiz":
        snapshot = _progress_snapshot(db, user)
        lesson_id = snapshot.get("next_lesson_id")
        questions = _questions(lesson_id) if lesson_id else []
        if not questions:
            send_message(chat_id, "Для текущей темы нет вопроса. Откройте урок в вебе: " + _web_link("/learn"))
            return
        question = questions[int(datetime.now(UTC).timestamp()) % len(questions)]
        send_message(chat_id, f"Вопрос по теме «{snapshot.get('next_lesson_title') or lesson_id}»:\n\n{question['prompt']}",
                     keyboard=quiz_keyboard(lesson_id, question))
    elif command == "/settings":
        send_message(chat_id, settings_text(db, user, binding),
                     keyboard=[[{"text": "Уведомления: вкл/выкл", "callback_data": "st:notify"}]])
    elif command == "/quiet":
        binding.quiet_hours, error = _parse_quiet(argument)
        if error:
            send_message(chat_id, error)
            return
        db.commit()
        send_message(chat_id, f"Тихие часы: {binding.quiet_hours or 'выключены'} (UTC).")
    elif command == "/unlink":
        revoke(db, binding)
        db.commit()
        send_message(chat_id, "Чат отвязан. История сохранена, очередь сообщений очищена.")
    else:
        send_message(chat_id, "Не знаю такую команду.\n\n" + HELP)


def _parse_quiet(argument: str) -> tuple[str | None, str | None]:
    if not argument or argument == "off":
        return None, None
    try:
        start_raw, end_raw = argument.split("-", 1)
        start = datetime.strptime(start_raw.strip(), QUIET_FORMAT).time()
        end = datetime.strptime(end_raw.strip(), QUIET_FORMAT).time()
    except ValueError:
        return None, "Формат: /quiet 22:00-08:00 (UTC) или /quiet off."
    if start == end:
        return None, "Начало и конец совпадают — тихие часы не имеют смысла."
    return f"{start.strftime(QUIET_FORMAT)}-{end.strftime(QUIET_FORMAT)}", None


def handle_callback(db: Session, chat_id: str, data: str, callback_id: str, message_id: int | None) -> None:
    binding = active_binding(db, chat_id)
    if binding is None:
        answer_callback(callback_id, "Чат не привязан")
        return
    user = db.get(User, binding.user_id)
    if user is None:
        answer_callback(callback_id, "Аккаунт недоступен")
        return
    if data == "st:notify":
        binding.notifications_enabled = not binding.notifications_enabled
        db.commit()
        answer_callback(callback_id, "Сохранено")
        if message_id:
            edit_message(chat_id, message_id, settings_text(db, user, binding))
        return
    if data.startswith("qz:"):
        _, lesson_id, question_id, index = data.split(":", 3)
        result = grade(lesson_id, question_id, int(index))
        if result is None:
            answer_callback(callback_id, "Вопрос недоступен")
            return
        correct, question = result
        record_quiz_evidence(db, user, lesson_id, question, question["choices"][int(index)], correct)
        verdict = "Верно." if correct else f"Неверно. Правильный ответ: {question['answer']}"
        answer_callback(callback_id, "Записано в прогресс")
        if message_id:
            edit_message(chat_id, message_id, f"{question['prompt']}\n\n{verdict}\n\n{question.get('explanation', '')}".strip())
        return
    answer_callback(callback_id, "Неизвестное действие")


# ---------------------------------------------------------------- webhook

def _text_of(update: dict) -> str:
    message = update.get("message") or {}
    return str(message.get("text") or "")


def handle_update(db: Session, update: dict) -> None:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if chat_id and _text_of(update).startswith("/"):
        throttle(db, scope="telegram_command", subject=chat_id, limit=30)
        handle_command(db, chat_id, _text_of(update), (message.get("from") or {}).get("username"))
        return
    callback = update.get("callback_query") or {}
    if callback:
        chat_id = str(((callback.get("message") or {}).get("chat") or {}).get("id") or "")
        if not chat_id:
            return
        throttle(db, scope="telegram_callback", subject=chat_id, limit=60)
        handle_callback(db, chat_id, str(callback.get("data") or ""), str(callback.get("id") or ""),
                        (callback.get("message") or {}).get("message_id"))
        return


def _remember(db: Session, update_id: int, chat_id: str | None) -> bool:
    """Store the update once; a redelivery is acknowledged and ignored."""
    db.add(TelegramUpdate(update_id=update_id, chat_id=chat_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


@router.post("/webhook/{secret}")
async def webhook(secret: str, request: Request, db: Session = Depends(get_db)) -> dict:
    expected = webhook_secret()
    token = bot_token()
    if expected is None or token is None:
        raise HTTPException(503, "Telegram channel is not configured")
    if not hmac.compare_digest(secret, expected):
        raise HTTPException(404, "Not found")
    header = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not hmac.compare_digest(header, expected):
        raise HTTPException(403, "Invalid webhook secret")
    raw = await request.body()
    if len(raw) > 128 * 1024:
        raise HTTPException(413, "Update is too large")
    try:
        update = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Malformed update") from None
    if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
        raise HTTPException(400, "Update without update_id")
    known = bool(update.get("message") or update.get("callback_query"))
    if not known:
        # Unknown kinds are refused instead of guessed at; Telegram stops retrying
        # once it sees 4xx, so this cannot loop.
        raise HTTPException(400, "Unsupported update type")
    chat = ((update.get("message") or {}).get("chat") or (update.get("callback_query") or {}).get("message", {}).get("chat") or {})
    if not _remember(db, update["update_id"], str(chat.get("id")) if chat.get("id") else None):
        return {"ok": True, "duplicate": True}
    handle_update(db, update)
    return {"ok": True}


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    return {
        "configured": configured(),
        "bot_username": os.getenv("TELEGRAM_BOT_USERNAME", "").strip() or None,
        "webhook_path_hint": "/telegram/webhook/<secret>",
    }


def quiet_now(binding: TelegramBinding) -> bool:
    """True while delivery should be postponed for this chat."""
    return in_quiet_hours(binding.quiet_hours)


def clear_updates(db: Session, older_than: timedelta = timedelta(days=7)) -> int:
    """Keep the dedupe ledger bounded."""
    cutoff = datetime.now(UTC) - older_than
    result = db.execute(delete(TelegramUpdate).where(TelegramUpdate.received_at < cutoff))
    db.commit()
    return int(result.rowcount or 0)


__all__ = [
    "active_binding",
    "bind",
    "binding_for_user",
    "bot_token",
    "clear_updates",
    "configured",
    "grade",
    "handle_callback",
    "handle_command",
    "handle_update",
    "link_url",
    "quiet_now",
    "quiz_keyboard",
    "render_progress",
    "render_today",
    "revoke",
    "router",
    "send_message",
    "settings_text",
    "webhook_secret",
]
