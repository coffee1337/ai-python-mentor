"""Weekly learning report: one generator, three renderings.

The bot, the email and the cabinet must show the same numbers for the same week.
They do, because all three render the single structure built here — there is no
second query path that could drift.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.account_models import NotificationOutbox, TelegramBinding
from app.db.models import LessonCompletion, User, UserMistake, UserSkill
from app.db.study_session_models import StudySession
from app.mailer import base_url


@dataclass(frozen=True)
class WeeklyReport:
    user_id: str
    week_start: str
    week_end: str
    lessons: int
    sessions: int
    minutes: int
    streak_days: int
    focus_skill: str | None
    focus_skill_label: str | None
    recurring_mistake: str | None
    next_goal: str

    def as_dict(self) -> dict:
        return asdict(self)


def week_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def build(db: Session, user: User, *, now: datetime | None = None) -> WeeklyReport:
    start, end = week_bounds(now)
    lessons = db.scalar(
        select(func.count()).select_from(LessonCompletion).where(
            LessonCompletion.user_id == user.id,
            LessonCompletion.completed_at >= start,
        )
    ) or 0
    sessions = db.scalar(
        select(func.count()).select_from(StudySession).where(
            StudySession.user_id == user.id,
            StudySession.started_at >= start,
        )
    ) or 0
    milliseconds = db.scalar(
        select(func.coalesce(func.sum(StudySession.accumulated_milliseconds), 0)).where(
            StudySession.user_id == user.id,
            StudySession.started_at >= start,
        )
    ) or 0
    days = db.scalars(
        select(func.date(LessonCompletion.completed_at)).where(
            LessonCompletion.user_id == user.id,
            LessonCompletion.completed_at >= start - timedelta(days=30),
        ).group_by(func.date(LessonCompletion.completed_at))
    ).all()
    streak, cursor = 0, (now or datetime.now(UTC)).date()
    normalized = {day.date() if isinstance(day, datetime) else datetime.fromisoformat(str(day)).date() for day in days}
    while cursor in normalized:
        streak += 1
        cursor -= timedelta(days=1)

    weakest = db.scalar(
        select(UserSkill).where(UserSkill.user_id == user.id, UserSkill.evidence_count > 0).order_by(UserSkill.knowledge_score.asc(), UserSkill.evidence_count.asc(), UserSkill.skill_id.asc())
    )
    mistake = db.scalar(
        select(UserMistake).where(UserMistake.user_id == user.id)
        .order_by(UserMistake.occurrence_count.desc(), UserMistake.misconception_code.asc())
    )
    focus_label = None
    if weakest is not None:
        focus_label = weakest.skill_id.split(".")[-1].replace("_", " ")
    return WeeklyReport(
        user_id=str(user.id),
        week_start=start.date().isoformat(),
        week_end=end.date().isoformat(),
        lessons=int(lessons),
        sessions=int(sessions),
        minutes=round(int(milliseconds) / 60000),
        streak_days=streak,
        focus_skill=weakest.skill_id if weakest is not None else None,
        focus_skill_label=focus_label,
        recurring_mistake=(mistake.misconception_code if mistake is not None else None),
        next_goal=(
            "Закрепить тему и пройти проверку без подсказок."
            if weakest is not None
            else "Пройти следующий урок и одну задачу с исполнением кода."
        ),
    )


def render_telegram(report: WeeklyReport) -> str:
    lines = [
        f"Итоги недели {report.week_start} — {report.week_end}",
        f"Уроков: {report.lessons} · занятий: {report.sessions} · минут: {report.minutes}",
        f"Серия дней подряд: {report.streak_days}",
    ]
    if report.focus_skill_label:
        lines.append(f"Слабое место: {report.focus_skill_label}")
    if report.recurring_mistake:
        lines.append(f"Повторяющаяся ошибка: {report.recurring_mistake}")
    lines.append(f"Цель на неделю: {report.next_goal}")
    lines.append(f"Продолжить: {base_url()}/dashboard")
    return "\n".join(lines)


def render_email(report: WeeklyReport) -> tuple[str, str]:
    subject = f"Итоги недели {report.week_start} — {report.week_end}"
    body = (
        f"Здравствуйте!\n\n{render_telegram(report)}\n\n"
        "Отчёт собран по вашим занятиям за семь дней.\n"
        "Настроить каналы можно в кабинете: " + base_url() + "/settings\n"
    )
    return subject, body


def render_web(report: WeeklyReport) -> dict:
    return report.as_dict()


def enqueue_weekly_reports(db: Session, *, now: datetime | None = None, limit: int = 500) -> int:
    """Queue one report per user per week for every channel the user has."""
    now = now or datetime.now(UTC)
    week_key = f"{now.isocalendar().year}W{now.isocalendar().week:02d}"
    queued = 0
    users = db.scalars(select(User).where(User.is_active.is_(True)).limit(limit)).all()
    for user in users:
        report = build(db, user, now=now)
        telegram = db.get(TelegramBinding, user.id)
        channels = ["email"]
        if telegram is not None and telegram.revoked_at is None and telegram.notifications_enabled:
            channels.append("telegram")
        for channel in channels:
            payload = {"report": report.as_dict()} if channel == "email" else {"text": render_telegram(report)}
            key = f"weekly-{week_key}-{channel}-{user.id}"
            if db.scalar(select(NotificationOutbox.id).where(NotificationOutbox.idempotency_key == key)):
                continue
            db.add(
                NotificationOutbox(
                    user_id=user.id,
                    channel=channel,
                    template="weekly_report",
                    payload=payload,
                    idempotency_key=key,
                    available_at=now,
                )
            )
            queued += 1
    db.commit()
    return queued


def report_for_user(db: Session, user_id: UUID, *, now: datetime | None = None) -> WeeklyReport | None:
    user = db.get(User, user_id)
    return build(db, user, now=now) if user is not None else None
