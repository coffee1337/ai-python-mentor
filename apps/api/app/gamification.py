"""Streak, XP, levels and achievements — derived, never stored twice.

Every number here is computed from evidence the learner already produced (lesson
completions, knowledge-check attempts, coding results). Nothing is awarded by the
model or by a claim: a streak is a run of days with a completion, XP is a fixed
price per verified action, and an achievement is a predicate over those facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CodingAttempt, KnowledgeCheckAttempt, LessonCompletion, User

# XP is a product constant, not a claim of skill: one verified action, one price.
XP_LESSON = 10
XP_KNOWLEDGE_CHECK = 5
XP_CODING_PASS = 15
LEVELS = (0, 100, 250, 450, 700, 1000)


@dataclass(frozen=True)
class Achievement:
    id: str
    title: str
    description: str
    earned: bool


@dataclass(frozen=True)
class Progress:
    xp: int
    level: int
    level_title: str
    next_level_xp: int | None
    streak_days: int
    longest_streak: int
    lessons: int
    knowledge_checks: int
    coding_passes: int
    achievements: list[Achievement] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "xp": self.xp,
            "level": self.level,
            "level_title": self.level_title,
            "next_level_xp": self.next_level_xp,
            "streak_days": self.streak_days,
            "longest_streak": self.longest_streak,
            "lessons": self.lessons,
            "knowledge_checks": self.knowledge_checks,
            "coding_passes": self.coding_passes,
            "achievements": [
                {"id": item.id, "title": item.title, "description": item.description, "earned": item.earned}
                for item in self.achievements
            ],
        }


def level_for(xp: int) -> tuple[int, str, int | None]:
    titles = ("Новичок", "Читающий код", "Пишущий функции", "Решающий задачи", "Собирающий сервис", "Backend-разработчик")
    level = 0
    for index, threshold in enumerate(LEVELS):
        if xp >= threshold:
            level = index
    next_level = LEVELS[level + 1] if level + 1 < len(LEVELS) else None
    return level, titles[min(level, len(titles) - 1)], next_level


def _days(db: Session, user_id) -> list:
    rows = db.scalars(
        select(func.date(LessonCompletion.completed_at)).where(LessonCompletion.user_id == user_id)
        .group_by(func.date(LessonCompletion.completed_at))
        .order_by(func.date(LessonCompletion.completed_at).desc())
    ).all()
    days = []
    for row in rows:
        days.append(row.date() if isinstance(row, datetime) else datetime.fromisoformat(str(row)).date())
    return days


def current_streak(days: list, *, today: datetime | None = None) -> int:
    """Days in a row with at least one completion, ending today or yesterday."""
    if not days:
        return 0
    cursor = (today or datetime.now(UTC)).date()
    ordered = sorted(set(days), reverse=True)
    if ordered[0] not in {cursor, cursor - timedelta(days=1)}:
        return 0
    streak, expected = 0, ordered[0]
    for day in ordered:
        if day == expected:
            streak += 1
            expected = day - timedelta(days=1)
        elif day < expected:
            break
    return streak


def longest_streak(days: list) -> int:
    ordered = sorted(set(days))
    best = run = 0
    previous = None
    for day in ordered:
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    return best


def build(db: Session, user: User, *, today: datetime | None = None) -> Progress:
    user_id = user.id
    lessons = db.scalar(select(func.count()).select_from(LessonCompletion).where(LessonCompletion.user_id == user_id)) or 0
    checks = db.scalar(
        select(func.count()).select_from(KnowledgeCheckAttempt).where(
            KnowledgeCheckAttempt.user_id == user_id, KnowledgeCheckAttempt.passed.is_(True)
        )
    ) or 0
    passes = db.scalar(
        select(func.count()).select_from(CodingAttempt).where(
            CodingAttempt.user_id == user_id, CodingAttempt.status == "passed"
        )
    ) or 0
    days = _days(db, user_id)
    streak = current_streak(days, today=today)
    best = longest_streak(days)
    xp = lessons * XP_LESSON + checks * XP_KNOWLEDGE_CHECK + passes * XP_CODING_PASS
    level, title, next_level = level_for(xp)
    achievements = [
        Achievement("first_step", "Первый шаг", "Первый завершённый урок", lessons >= 1),
        Achievement("check_master", "Проверка пройдена", "Три пройденных проверки знаний", checks >= 3),
        Achievement("code_runs", "Код работает", "Первое задание с исполнением кода", passes >= 1),
        Achievement("ten_lessons", "Десять уроков", "Десять завершённых уроков", lessons >= 10),
        Achievement("week_streak", "Неделя подряд", "Семь дней занятий без пропуска", best >= 7),
        Achievement("level_three", "Третий уровень", "450 XP набрано", level >= 3),
    ]
    return Progress(
        xp=xp,
        level=level,
        level_title=title,
        next_level_xp=next_level,
        streak_days=streak,
        longest_streak=best,
        lessons=int(lessons),
        knowledge_checks=int(checks),
        coding_passes=int(passes),
        achievements=achievements,
    )
