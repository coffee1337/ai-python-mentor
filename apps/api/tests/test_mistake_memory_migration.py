from datetime import datetime, timezone
import runpy
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def _config():
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    return config


def test_mistake_memory_seed_is_idempotent_and_downgrade_removes_new_tables(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'mistake-memory.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = _config()

    command.upgrade(config, "head")
    engine = create_engine(url)
    seed = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0023_mistake_memory.py")
    )["seed_misconception_catalog"]
    mapping_seed = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "versions"
            / "0024_authored_mistake_mappings.py"
        )
    )["seed_authored_mappings"]
    assessment_seed = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "versions"
            / "0025_assessment_mistake_mappings.py"
        )
    )["seed_assessment_mappings"]
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        seed(connection)
        mapping_seed(connection)
        assessment_seed(connection)
        codes = connection.execute(
            text("SELECT code, skill_id FROM misconceptions ORDER BY code")
        ).all()
        assert codes == [
            ("mis-assignment-no-update-v1", "python.variables"),
            ("mis-assignment-square-v1", "python.variables"),
            ("mis-boolean-assignment-v1", "python.conditionals"),
            ("mis-boolean-negative-v1", "python.conditionals"),
            ("mis-branch-strict-boundary-v1", "python.conditionals"),
            ("mis-branch-type-v1", "python.conditionals"),
            ("mis-cond-boundary-both-v1", "python.conditionals"),
            ("mis-cond-boundary-excluded-v1", "python.conditionals"),
            ("mis-cond-else-always-v1", "python.conditionals"),
            ("mis-cond-else-syntax-v1", "python.conditionals"),
            ("mis-types-none-v1", "python.variables"),
            ("mis-types-string-v1", "python.variables"),
            ("mis-var-output-first-v1", "python.variables"),
            ("mis-var-output-partial-v1", "python.variables"),
            ("mis-var-reassign-compare-v1", "python.variables"),
            ("mis-var-reassign-second-v1", "python.variables"),
        ]
        assert len(codes) == 16
        assert connection.scalar(text("SELECT count(*) FROM misconception_versions")) == 16
        assert connection.scalar(text("SELECT count(*) FROM misconception_mappings")) == 20
        mappings = connection.execute(
            text(
                "SELECT source_type, exercise_id, exercise_version, question_id, "
                "wrong_choice, misconception_code FROM misconception_mappings "
                "WHERE source_type = 'knowledge_check_response' "
                "ORDER BY exercise_id, question_id, wrong_choice"
            )
        ).all()
        assert set(mappings) == {
            (
                "knowledge_check_response",
                "conditions-v1",
                1,
                "conditions-boundary-v1",
                "minor",
                "mis-cond-boundary-excluded-v1",
            ),
            (
                "knowledge_check_response",
                "conditions-v1",
                1,
                "conditions-boundary-v1",
                "Обе",
                "mis-cond-boundary-both-v1",
            ),
            (
                "knowledge_check_response",
                "conditions-v1",
                1,
                "conditions-else-v1",
                "Всегда после if",
                "mis-cond-else-always-v1",
            ),
            (
                "knowledge_check_response",
                "conditions-v1",
                1,
                "conditions-else-v1",
                "Только при синтаксической ошибке",
                "mis-cond-else-syntax-v1",
            ),
            (
                "knowledge_check_response",
                "variables-v1",
                1,
                "variables-output-v1",
                "2",
                "mis-var-output-partial-v1",
            ),
            (
                "knowledge_check_response",
                "variables-v1",
                1,
                "variables-output-v1",
                "4",
                "mis-var-output-first-v1",
            ),
            (
                "knowledge_check_response",
                "variables-v1",
                1,
                "variables-reassignment-v1",
                "Создаёт вторую переменную x",
                "mis-var-reassign-second-v1",
            ),
            (
                "knowledge_check_response",
                "variables-v1",
                1,
                "variables-reassignment-v1",
                "Сравнивает x с 1",
                "mis-var-reassign-compare-v1",
            ),
        }
        # Re-running every seed is a no-op, including mapping identities.
        seed(connection)
        mapping_seed(connection)
        assessment_seed(connection)
        assert connection.scalar(text("SELECT count(*) FROM misconception_versions")) == 16
        assert connection.scalar(text("SELECT count(*) FROM misconception_mappings")) == 20
        assert connection.scalar(
            text(
                "SELECT count(*) FROM misconception_mappings "
                "WHERE source_type = 'assessment_response'"
            )
        ) == 12

        user_id = uuid4().hex
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": user_id, "email": "mistake-memory@example.com", "password": "sentinel"},
        )
        version_id = connection.scalar(
            text(
                "SELECT id FROM misconception_versions "
                "WHERE misconception_code = 'mis-var-output-first-v1'"
            )
        )
        user_mistake_id = uuid4().hex
        occurred_at = datetime(2026, 10, 3, tzinfo=timezone.utc)
        connection.execute(
            text(
                "INSERT INTO user_mistakes "
                "(id, user_id, misconception_code, skill_id, lesson_id, occurrence_count, "
                "first_seen_at, last_seen_at, last_source_type, last_source_id) "
                "VALUES (:id, :user_id, 'mis-var-output-first-v1', 'python.variables', "
                "'variables-v1', 1, :occurred_at, :occurred_at, "
                "'knowledge_check_response', 'response-1')"
            ),
            {"id": user_mistake_id, "user_id": user_id, "occurred_at": occurred_at},
        )
        connection.execute(
            text(
                "INSERT INTO mistake_occurrences "
                "(id, user_id, user_mistake_id, misconception_code, misconception_version_id, "
                "source_type, source_id, lesson_id, occurred_at) "
                "VALUES (:id, :user_id, :user_mistake_id, :code, :version_id, 'knowledge_check_response', "
                "'response-1', 'variables-v1', :occurred_at)"
            ),
            {
                "id": uuid4().hex,
                "user_id": user_id,
                "user_mistake_id": user_mistake_id,
                "code": "mis-var-output-first-v1",
                "version_id": version_id,
                "occurred_at": occurred_at,
            },
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "INSERT INTO mistake_occurrences "
                    "(id, user_id, user_mistake_id, misconception_code, misconception_version_id, "
                    "source_type, source_id, lesson_id, occurred_at) "
                    "VALUES (:id, :user_id, :user_mistake_id, :code, :version_id, 'knowledge_check_response', "
                    "'response-1', 'variables-v1', :occurred_at)"
                ),
                {
                    "id": uuid4().hex,
                    "user_id": user_id,
                    "user_mistake_id": user_mistake_id,
                    "code": "mis-var-output-first-v1",
                    "version_id": version_id,
                    "occurred_at": occurred_at,
                },
            )
        assert connection.scalar(text("SELECT count(*) FROM mistake_occurrences")) == 1

        other_user_id = uuid4().hex
        other_mistake_id = uuid4().hex
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": other_user_id, "email": "other-mistake-memory@example.com", "password": "sentinel"},
        )
        connection.execute(
            text(
                "INSERT INTO user_mistakes "
                "(id, user_id, misconception_code, skill_id, lesson_id, occurrence_count, "
                "first_seen_at, last_seen_at, last_source_type, last_source_id) "
                "VALUES (:id, :user_id, 'mis-var-output-first-v1', 'python.variables', "
                "'variables-v1', 1, :occurred_at, :occurred_at, "
                "'knowledge_check_response', 'other-response')"
            ),
            {"id": other_mistake_id, "user_id": other_user_id, "occurred_at": occurred_at},
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "INSERT INTO mistake_occurrences "
                    "(id, user_id, user_mistake_id, misconception_code, misconception_version_id, "
                    "source_type, source_id, lesson_id, occurred_at) "
                    "VALUES (:id, :user_id, :user_mistake_id, :code, :version_id, "
                    "'knowledge_check_response', 'foreign-response', 'variables-v1', :occurred_at)"
                ),
                {
                    "id": uuid4().hex,
                    "user_id": user_id,
                    "user_mistake_id": other_mistake_id,
                    "code": "mis-var-output-first-v1",
                    "version_id": version_id,
                    "occurred_at": occurred_at,
                },
            )

    command.downgrade(config, "0024_authored_mistake_mappings")
    with engine.connect() as connection:
        table_names = set(inspect(connection).get_table_names())
        assert "misconception_mappings" in table_names
        assert "user_mistakes" in table_names
        assert connection.scalar(text("SELECT count(*) FROM mistake_occurrences")) == 1
        assert connection.scalar(
            text(
                "SELECT count(*) FROM misconception_mappings "
                "WHERE source_type = 'assessment_response'"
            )
        ) == 0
        assert connection.scalar(
            text(
                "SELECT count(*) FROM misconception_versions "
                "WHERE misconception_code = 'mis-types-string-v1'"
            )
        ) == 0

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM misconception_mappings")) == 20
        assert connection.scalar(text("SELECT count(*) FROM mistake_occurrences")) == 1

    command.downgrade(config, "0023_mistake_memory")
    with engine.connect() as connection:
        table_names = set(inspect(connection).get_table_names())
        assert "misconception_mappings" not in table_names
        assert connection.scalar(text("SELECT count(*) FROM mistake_occurrences")) == 1
        assert connection.scalar(
            text(
                "SELECT count(*) FROM misconception_versions "
                "WHERE misconception_code = 'mis-var-output-first-v1'"
            )
        ) == 1

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM misconception_mappings")) == 20
        assert connection.scalar(text("SELECT count(*) FROM mistake_occurrences")) == 1

    command.downgrade(config, "0022_lesson_sessions")
    with engine.connect() as connection:
        table_names = set(inspect(connection).get_table_names())
        assert "misconceptions" not in table_names
        assert "misconception_versions" not in table_names
        assert "misconception_mappings" not in table_names
        assert "user_mistakes" not in table_names
        assert "mistake_occurrences" not in table_names
        assert connection.scalar(
            text("SELECT email FROM users WHERE email = 'mistake-memory@example.com'")
        ) == "mistake-memory@example.com"

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM misconceptions")) == 16
        assert connection.scalar(text("SELECT count(*) FROM misconception_versions")) == 16
        assert connection.scalar(text("SELECT count(*) FROM misconception_mappings")) == 20
    engine.dispose()
