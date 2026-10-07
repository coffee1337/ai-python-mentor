"""Draft schema rollback removes new drafts while preserving existing history."""
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_draft_migration_roundtrip_preserves_existing_account_and_snapshot(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'draft-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0037_lesson_reflections")
    engine = create_engine(url)
    owner, version = uuid4().hex, uuid4().hex
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id,email,password_hash) VALUES (:id,'draft-sentinel@example.com','sentinel')"), {"id": owner})
        connection.execute(text("INSERT INTO exercise_versions (id,exercise_id,version,lesson_id,content_snapshot) VALUES (:id,'sentinel-v1',1,'sentinel-v1',:snapshot)"), {"id": version, "snapshot": '{"sentinel":"immutable"}'})
        connection.execute(text("INSERT INTO lesson_reflections (id,user_id,exercise_version_id,lesson_id,idempotency_key,text,feedback) VALUES (:id,:owner,:version,'sentinel-v1','sentinel-key','retained reflection','ungraded')"), {"id": uuid4().hex, "owner": owner, "version": version})
    try:
        command.upgrade(config, "0038_study_drafts")
        assert "study_drafts" in inspect(engine).get_table_names()
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO study_drafts (id,user_id,kind,resource_id,version,milestone_id,exercise_version_id,revision,content) VALUES (:id,:owner,'reflection','sentinel-v1',1,'',:version,2,NULL)"), {"id": uuid4().hex, "owner": owner, "version": version})
        command.downgrade(config, "0037_lesson_reflections")
        assert "study_drafts" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT email FROM users WHERE id=:id"), {"id": owner}) == "draft-sentinel@example.com"
            assert connection.scalar(text("SELECT text FROM lesson_reflections WHERE user_id=:id"), {"id": owner}) == "retained reflection"
            assert connection.scalar(text("SELECT content_snapshot FROM exercise_versions WHERE id=:id"), {"id": version}) == '{"sentinel":"immutable"}'
        command.upgrade(config, "0038_study_drafts")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM study_drafts")) == 0
            assert connection.scalar(text("SELECT count(*) FROM lesson_reflections WHERE user_id=:id"), {"id": owner}) == 1
    finally:
        engine.dispose()
