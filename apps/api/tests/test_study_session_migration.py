"""The timer migration is additive and its rollback preserves older data."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def test_timer_schema_roundtrip_keeps_user_and_older_feature_sentinel(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'study-session-migration.sqlite3').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0038_study_drafts")
    engine = create_engine(url)
    owner = uuid4().hex
    stamp = datetime(2026, 10, 7, 9, tzinfo=timezone.utc)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users(id,email,password_hash) VALUES(:id,'timer-migration@example.com','sentinel')"), {"id": owner})
            connection.execute(text("INSERT INTO learner_projects(id,user_id,template_id,template_snapshot) "
                                    "VALUES(:id,:owner,'timer-migration-sentinel','{}')"), {"id": uuid4().hex, "owner": owner})
        command.upgrade(config, "0039_study_sessions")
        query = text("INSERT INTO study_sessions(id,user_id,status,revision,started_at,updated_at,ended_at,last_activity_at,"
                     "accumulated_milliseconds,focus_snapshot,estimated_minutes,target_minutes) "
                     "VALUES(:id,:owner,:status,1,:stamp,:stamp,:ended,:last,:duration,'[]',0,60)")
        paused_id = uuid4().hex
        with engine.begin() as connection:
            connection.execute(query, {"id": paused_id, "owner": owner, "status": "paused", "stamp": stamp,
                                       "ended": None, "last": None, "duration": 12000})
            connection.execute(query, {"id": uuid4().hex, "owner": owner, "status": "completed", "stamp": stamp,
                                       "ended": stamp, "last": None, "duration": 24000})
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(query, {"id": uuid4().hex, "owner": owner, "status": "active", "stamp": stamp,
                                           "ended": None, "last": stamp, "duration": 0})
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(query, {"id": uuid4().hex, "owner": owner, "status": "completed", "stamp": stamp,
                                           "ended": stamp, "last": None, "duration": 28800001})
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT accumulated_milliseconds FROM study_sessions WHERE id=:id"), {"id": paused_id}) == 12000
        command.downgrade(config, "0038_study_drafts")
        assert "study_sessions" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT email FROM users WHERE id=:id"), {"id": owner}) == "timer-migration@example.com"
            assert connection.scalar(text("SELECT count(*) FROM learner_projects WHERE user_id=:id"), {"id": owner}) == 1
            assert connection.scalar(text("SELECT count(*) FROM skill_evidence")) == 0
        command.upgrade(config, "0039_study_sessions")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM study_sessions")) == 0
            assert connection.scalar(text("SELECT count(*) FROM learner_projects WHERE user_id=:id"), {"id": owner}) == 1
    finally:
        engine.dispose()
