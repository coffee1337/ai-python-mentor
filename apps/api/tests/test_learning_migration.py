from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_upgrade_preserves_users_and_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0002_auth_onboarding")
    engine = create_engine(url)
    user_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
                           {"id": user_id, "email": "existing@example.com", "password": "existing-hash"})
    command.upgrade(config, "head")
    assert "lesson_completions" in inspect(engine).get_table_names()
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT email FROM users")) == "existing@example.com"
        connection.execute(text("INSERT INTO lesson_completions (user_id, lesson_id, answer, evidence_type) VALUES (:id, 'variables-v1', '6', 'authored_quiz_correct')"), {"id": user_id})
    command.downgrade(config, "0002_auth_onboarding")
    assert "lesson_completions" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM users")) == 1
    command.upgrade(config, "head")
    engine.dispose()
