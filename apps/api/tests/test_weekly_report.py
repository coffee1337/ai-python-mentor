"""Weekly report: one generator, three channels, week-level idempotency.

If the bot, the email and the cabinet ever disagree, this suite fails: all three
render the same `WeeklyReport` structure built from one query path.
"""
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.account_models import NotificationOutbox, TelegramBinding
from app.db.base import Base
from app.db.models import LessonCompletion, User
from app.db.study_session_models import StudySession
from app.mailer import MailError
from app.mailer import render as render_mail
from app.telegram_bot import quiet_now
from app.weekly_report import (
    build,
    enqueue_weekly_reports,
    render_email,
    render_telegram,
    render_web,
)


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    Base.metadata.drop_all(engine)


@pytest.fixture()
def learner(session_factory):
    with session_factory() as db:
        user = User(email="weekly@example.com", password_hash="x", is_active=True)
        db.add(user)
        db.flush()
        now = datetime.now(UTC)
        for days_ago in (0, 1, 2):
            db.add(
                LessonCompletion(
                    user_id=user.id,
                    lesson_id=f"lesson-{days_ago}",
                    answer="knowledge_check",
                    completed_at=now - timedelta(days=days_ago),
                )
            )
        db.add(
            StudySession(
                user_id=user.id,
                status="completed",
                revision=1,
                started_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
                ended_at=now - timedelta(days=1) + timedelta(minutes=25),
                accumulated_milliseconds=25 * 60 * 1000,
                focus_snapshot=[],
                estimated_minutes=25,
                target_minutes=25,
            )
        )
        db.commit()
        return user.id


def test_one_structure_feeds_three_channels(session_factory, learner):
    with session_factory() as db:
        report = build(db, db.get(User, learner))
    telegram_text = render_telegram(report)
    subject, body = render_email(report)
    web = render_web(report)
    assert web["lessons"] == 3 and web["minutes"] == 25 and web["sessions"] == 1
    assert report.lessons == 3 and report.minutes == 25
    assert str(report.lessons) in telegram_text and str(report.minutes) in telegram_text
    assert str(report.lessons) in body and subject.startswith("Итоги недели")
    assert json.loads(json.dumps(web))["week_start"] == report.week_start


def test_email_template_uses_the_same_generator(session_factory, learner):
    with session_factory() as db:
        report = build(db, db.get(User, learner))
    subject, body = render_mail("weekly_report", {"report": render_web(report)})
    assert subject == render_email(report)[0]
    assert f"Уроков: {report.lessons}" in body
    with pytest.raises(MailError):
        render_mail("weekly_report", {"report": {"nonsense": True}})


def test_reports_are_queued_once_per_week_and_channel(session_factory, learner):
    with session_factory() as db:
        db.add(TelegramBinding(user_id=learner, chat_id="777"))
        db.commit()
        first = enqueue_weekly_reports(db)
        second = enqueue_weekly_reports(db)
        rows = db.scalars(select(NotificationOutbox)).all()
    assert first == 2 and second == 0, "по одному письму на канал за неделю"
    assert {row.channel for row in rows} == {"email", "telegram"}
    telegram_row = next(row for row in rows if row.channel == "telegram")
    assert "Итоги недели" in telegram_row.payload["text"]


def test_revoked_or_disabled_binding_gets_no_telegram_report(session_factory, learner):
    with session_factory() as db:
        db.add(TelegramBinding(user_id=learner, chat_id="778", notifications_enabled=False))
        db.commit()
        assert enqueue_weekly_reports(db) == 1
        channels = {row.channel for row in db.scalars(select(NotificationOutbox)).all()}
    assert channels == {"email"}


def test_quiet_hours_window_wraps_midnight():
    binding = TelegramBinding(user_id=None, chat_id="1", quiet_hours="23:00-07:00")
    hour = datetime.now(UTC).hour
    expected = hour >= 23 or hour < 7
    assert quiet_now(binding) is expected
    binding_endless = TelegramBinding(user_id=None, chat_id="2", quiet_hours="00:00-23:59")
    assert quiet_now(binding_endless) is True
    binding_broken = TelegramBinding(user_id=None, chat_id="3", quiet_hours="garbage")
    assert quiet_now(binding_broken) is False
