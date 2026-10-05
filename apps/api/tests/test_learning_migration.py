import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from app.exercise_hints import _persisted_idempotency_key


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


def test_0028_mapping_upgrade_downgrade_preserves_learning_history(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'lesson-skill-0028-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0027_review_api")
    engine = create_engine(url)

    user_id = uuid4().hex
    version_id = uuid4().hex
    old_primary_link_id = uuid4().hex
    old_secondary_link_id = uuid4().hex
    conditions_link_id = uuid4().hex
    snapshot = {
        "schema_version": 1,
        "exercise_id": "variables-v1",
        "version": 1,
        "lesson": {"id": "variables-v1", "skill_id": "python.variables"},
    }
    with engine.begin() as connection:
        for skill_id, name in (
            ("python.variables", "variables"),
            ("python.data_types", "data types"),
            ("python.conditionals", "conditionals"),
        ):
            connection.execute(
                text(
                    "INSERT INTO skills (id, name, category, description) "
                    "VALUES (:id, :name, 'python.core', 'migration sentinel')"
                ),
                {"id": skill_id, "name": name},
            )
        connection.execute(
            text(
                "INSERT INTO lesson_skills (id, lesson_id, skill_id) "
                "VALUES (:id, 'variables-v1', 'python.variables')"
            ),
            {"id": old_primary_link_id},
        )
        connection.execute(
            text(
                "INSERT INTO lesson_skills (id, lesson_id, skill_id) "
                "VALUES (:id, 'variables-v1', 'python.data_types')"
            ),
            {"id": old_secondary_link_id},
        )
        connection.execute(
            text(
                "INSERT INTO lesson_skills (id, lesson_id, skill_id) "
                "VALUES (:id, 'conditions-v1', 'python.conditionals')"
            ),
            {"id": conditions_link_id},
        )
        connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash) "
                "VALUES (:id, 'mapping-roundtrip@example.com', 'sentinel')"
            ),
            {"id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions "
                "(id, exercise_id, version, lesson_id, content_snapshot) "
                "VALUES (:id, 'variables-v1', 1, 'variables-v1', :snapshot)"
            ),
            {"id": version_id, "snapshot": json.dumps(snapshot)},
        )
        connection.execute(
            text(
                "INSERT INTO lesson_completions "
                "(user_id, lesson_id, answer, exercise_version_id, evidence_type) "
                "VALUES (:user_id, 'variables-v1', '6', :version_id, "
                "'authored_quiz_correct')"
            ),
            {"user_id": user_id, "version_id": version_id},
        )

    command.upgrade(config, "0028_correct_variables_data_types_mapping")
    with engine.connect() as connection:
        links = set(
            connection.execute(
                text("SELECT lesson_id, skill_id FROM lesson_skills")
            ).all()
        )
        assert links == {
            ("variables-v1", "python.variables"),
            ("data-types-v1", "python.data_types"),
            ("conditions-v1", "python.conditionals"),
        }
        assert connection.scalar(
            text(
                "SELECT count(*) FROM lesson_completions "
                "WHERE user_id = :user_id AND lesson_id = 'variables-v1' "
                "AND exercise_version_id = :version_id"
            ),
            {"user_id": user_id, "version_id": version_id},
        ) == 1
        assert json.loads(connection.scalar(
            text("SELECT content_snapshot FROM exercise_versions WHERE id = :id"),
            {"id": version_id},
        )) == snapshot

    command.downgrade(config, "0027_review_api")
    with engine.connect() as connection:
        links = set(
            connection.execute(
                text("SELECT lesson_id, skill_id FROM lesson_skills")
            ).all()
        )
        assert links == {
            ("variables-v1", "python.variables"),
            ("variables-v1", "python.data_types"),
            ("conditions-v1", "python.conditionals"),
        }
        assert connection.scalar(
            text("SELECT count(*) FROM lesson_completions WHERE user_id = :id"),
            {"id": user_id},
        ) == 1
        assert json.loads(connection.scalar(
            text("SELECT content_snapshot FROM exercise_versions WHERE id = :id"),
            {"id": version_id},
        )) == snapshot

    command.upgrade(config, "0028_correct_variables_data_types_mapping")
    with engine.connect() as connection:
        assert set(
            connection.execute(
                text("SELECT lesson_id, skill_id FROM lesson_skills")
            ).all()
        ) == {
            ("variables-v1", "python.variables"),
            ("data-types-v1", "python.data_types"),
            ("conditions-v1", "python.conditionals"),
        }
    engine.dispose()


def test_skill_evidence_constraints_roundtrip_0019_0020(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'evidence-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0019_restrict_exercise_version_deletion")
    engine = create_engine(url)
    user_id = uuid4().hex
    evidence_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": user_id, "email": "evidence-roundtrip@example.com", "password": "sentinel"},
        )
        connection.execute(
            text(
                "INSERT INTO skills (id, name, category, description) "
                "VALUES ('python.variables', 'Variables', 'python', 'sentinel')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO skill_evidence "
                "(id, user_id, skill_id, source_type, source_id, result_score, assisted, "
                "hint_count, occurred_at, idempotency_key) "
                "VALUES (:id, :user_id, 'python.variables', 'assessment_response', "
                "'sentinel-source', 1.0, 0, 0, CURRENT_TIMESTAMP, 'sentinel-key')"
            ),
            {"id": evidence_id, "user_id": user_id},
        )

    command.upgrade(config, "head")
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO skill_evidence "
                    "(id, user_id, skill_id, source_type, source_id, result_score, assisted, "
                    "hint_count, occurred_at, idempotency_key) "
                    "VALUES (:id, :user_id, 'python.variables', 'assessment_response', "
                    "'invalid-source', 1.0, 0, 1, CURRENT_TIMESTAMP, 'invalid-key')"
                ),
                {"id": uuid4().hex, "user_id": user_id},
            )

    command.downgrade(config, "0019_restrict_exercise_version_deletion")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
        ) == "evidence-roundtrip@example.com"
        assert connection.scalar(
            text("SELECT count(*) FROM skill_evidence WHERE id = :id"), {"id": evidence_id}
        ) == 1
    engine.dispose()


def test_knowledge_check_session_migration_roundtrip_preserves_sentinel(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'knowledge-check-session-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0020_skill_evidence_assistance_constraints")
    engine = create_engine(url)
    user_id = uuid4().hex
    version_id = uuid4().hex
    session_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": user_id, "email": "knowledge-session@example.com", "password": "sentinel"},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions (id, exercise_id, version, lesson_id) "
                "VALUES (:id, 'variables-v1', 1, 'variables-v1')"
            ),
            {"id": version_id},
        )
    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO knowledge_check_sessions "
                "(id, user_id, lesson_id, exercise_version_id, created_at, consumed_at) "
                "VALUES (:id, :user_id, 'variables-v1', :version_id, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": session_id, "user_id": user_id, "version_id": version_id},
        )

    command.downgrade(config, "0020_skill_evidence_assistance_constraints")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
        ) == "knowledge-session@example.com"
        row = connection.execute(
            text(
                "SELECT user_id, lesson_id, exercise_version_id, consumed_at "
                "FROM knowledge_check_sessions WHERE id = :id"
            ),
            {"id": session_id},
        ).one()
        assert row.user_id == user_id
        assert row.lesson_id == "variables-v1"
        assert row.exercise_version_id == version_id
        assert row.consumed_at is not None
    engine.dispose()


def test_lesson_session_migration_roundtrip_preserves_binding_and_completion(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'lesson-session-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0021_knowledge_check_sessions")
    engine = create_engine(url)
    user_id = uuid4().hex
    version_id = uuid4().hex
    session_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": user_id, "email": "lesson-session@example.com", "password": "sentinel"},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions (id, exercise_id, version, lesson_id) "
                "VALUES (:id, 'variables-v1', 1, 'variables-v1')"
            ),
            {"id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO lesson_completions (user_id, lesson_id, answer, evidence_type) "
                "VALUES (:user_id, 'conditions-v1', 'adult', 'authored_quiz_correct')"
            ),
            {"user_id": user_id},
        )

    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO lesson_sessions "
                "(id, user_id, lesson_id, exercise_version_id, created_at) "
                "VALUES (:id, :user_id, 'variables-v1', :version_id, CURRENT_TIMESTAMP)"
            ),
            {"id": session_id, "user_id": user_id, "version_id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO lesson_completions "
                "(user_id, lesson_id, answer, exercise_version_id, evidence_type) "
                "VALUES (:user_id, 'variables-v1', '6', :version_id, 'authored_quiz_correct')"
            ),
            {"user_id": user_id, "version_id": version_id},
        )

    command.downgrade(config, "0021_knowledge_check_sessions")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        session = connection.execute(
            text(
                "SELECT user_id, lesson_id, exercise_version_id, consumed_at "
                "FROM lesson_sessions WHERE id = :id"
            ),
            {"id": session_id},
        ).one()
        assert session.user_id == user_id
        assert session.lesson_id == "variables-v1"
        assert session.exercise_version_id == version_id
        completion = connection.execute(
            text(
                "SELECT answer, exercise_version_id FROM lesson_completions "
                "WHERE user_id = :user_id AND lesson_id = 'variables-v1'"
            ),
            {"user_id": user_id},
        ).one()
        assert completion.answer == "6"
        assert completion.exercise_version_id == version_id
        assert connection.execute(
            text(
                "SELECT answer, exercise_version_id FROM lesson_completions "
                "WHERE user_id = :user_id AND lesson_id = 'conditions-v1'"
            ),
            {"user_id": user_id},
        ).one() == ("adult", None)
    engine.dispose()


def test_exercise_snapshot_migration_roundtrip_preserves_sentinel(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'snapshot-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0015_exercise_hint_ladder")
    engine = create_engine(url)
    user_id = uuid4().hex
    version_id = uuid4().hex
    newer_version_id = uuid4().hex
    run_id = uuid4().hex
    response_id = uuid4().hex
    attempt_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": user_id, "email": "snapshot-sentinel@example.com", "password": "sentinel"},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions (id, exercise_id, version, lesson_id) "
                "VALUES (:id, 'variables-v1', 1, 'variables-v1')"
            ),
            {"id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions (id, exercise_id, version, lesson_id) "
                "VALUES (:id, 'variables-v1', 2, 'variables-v1')"
            ),
            {"id": newer_version_id},
        )
        connection.execute(
            text(
                "INSERT INTO assessment_runs "
                "(id, user_id, status, asked_question_ids) "
                "VALUES (:id, :user_id, 'completed', '[]')"
            ),
            {"id": run_id, "user_id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO assessment_responses "
                "(id, run_id, question_id, skill_id, difficulty, answer, is_correct) "
                "VALUES (:id, :run_id, 'variables-v1', 'python.variables', 0.1, '6', 1)"
            ),
            {"id": response_id, "run_id": run_id},
        )
        connection.execute(
            text(
                "INSERT INTO knowledge_check_attempts "
                "(id, user_id, lesson_id, skill_id, score, passed) "
                "VALUES (:id, :user_id, 'variables-v1', 'python.variables', 1.0, 1)"
            ),
            {"id": attempt_id, "user_id": user_id},
        )

    command.upgrade(config, "head")
    assert "exercise_version_id" in {
        column["name"] for column in inspect(engine).get_columns("assessment_responses")
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT email FROM users WHERE id = :id"), {"id": user_id}) == "snapshot-sentinel@example.com"
        snapshot = connection.scalar(
            text("SELECT content_snapshot FROM exercise_versions WHERE id = :id"),
            {"id": version_id},
        )
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        assert snapshot["lesson"]["answer"] == "6"
        assert snapshot["hints"][0]["text"].startswith("Проследи")
        assert connection.scalar(
            text("SELECT exercise_version_id FROM assessment_responses WHERE id = :id"),
            {"id": response_id},
        ) == version_id
        assert connection.scalar(
            text("SELECT exercise_version_id FROM knowledge_check_attempts WHERE id = :id"),
            {"id": attempt_id},
        ) == version_id
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE knowledge_check_attempts SET exercise_version_id = :version_id "
                "WHERE id = :id"
            ),
            {"version_id": newer_version_id, "id": attempt_id},
        )

    command.downgrade(config, "0015_exercise_hint_ladder")
    assert "exercise_version_id" not in {
        column["name"] for column in inspect(engine).get_columns("assessment_responses")
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT email FROM users WHERE id = :id"), {"id": user_id}) == "snapshot-sentinel@example.com"
        assert connection.scalar(
            text("SELECT question_id FROM assessment_responses WHERE id = :id"),
            {"id": response_id},
        ) == "variables-v1"
        assert connection.scalar(
            text("SELECT lesson_id FROM knowledge_check_attempts WHERE id = :id"),
            {"id": attempt_id},
        ) == "variables-v1"
        assert connection.scalar(
            text("SELECT count(*) FROM exercise_version_snapshot_downgrade")
        ) == 2

    command.upgrade(config, "head")
    assert "exercise_version_snapshot_downgrade" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT exercise_version_id FROM assessment_responses WHERE id = :id"),
            {"id": response_id},
        ) == version_id
        assert connection.scalar(
            text("SELECT exercise_version_id FROM knowledge_check_attempts WHERE id = :id"),
            {"id": attempt_id},
        ) == newer_version_id
        restored = connection.scalar(
            text("SELECT content_snapshot FROM exercise_versions WHERE id = :id"),
            {"id": version_id},
        )
        if isinstance(restored, str):
            restored = json.loads(restored)
        assert restored == snapshot
    engine.dispose()


def test_exercise_content_snapshot_roundtrip_0016_head_0016_head(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'content-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0016_exercise_version_snapshots")
    engine = create_engine(url)
    version_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO exercise_versions (id, exercise_id, version, lesson_id) "
                "VALUES (:id, 'variables-v1', 1, 'variables-v1')"
            ),
            {"id": version_id},
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        snapshot = connection.scalar(
            text("SELECT content_snapshot FROM exercise_versions WHERE id = :id"),
            {"id": version_id},
        )
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        assert snapshot["exercise_id"] == "variables-v1"

    command.downgrade(config, "0016_exercise_version_snapshots")
    assert "content_snapshot" not in {
        column["name"] for column in inspect(engine).get_columns("exercise_versions")
    }
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT count(*) FROM exercise_versions WHERE id = :id"),
            {"id": version_id},
        ) == 1

    command.upgrade(config, "head")
    with engine.connect() as connection:
        restored = connection.scalar(
            text("SELECT content_snapshot FROM exercise_versions WHERE id = :id"),
            {"id": version_id},
        )
        if isinstance(restored, str):
            restored = json.loads(restored)
        assert restored == snapshot
    engine.dispose()


def test_assessment_run_version_roundtrip_0017_0018_preserves_binding(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'assessment-run-version-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0017_exercise_content_snapshots")
    engine = create_engine(url)
    user_id = uuid4().hex
    version_id = uuid4().hex
    run_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": user_id, "email": "assessment-run-roundtrip@example.com", "password": "sentinel"},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions (id, exercise_id, version, lesson_id) "
                "VALUES (:id, 'variables-v1', 1, 'variables-v1')"
            ),
            {"id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO assessment_runs "
                "(id, user_id, status, current_question_id, asked_question_ids) "
                "VALUES (:id, :user_id, 'in_progress', 'variables-v1', '[]')"
            ),
            {"id": run_id, "user_id": user_id},
        )

    command.upgrade(config, "0018_assessment_run_exercise_version")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE assessment_runs SET current_exercise_version_id = :version_id "
                "WHERE id = :run_id"
            ),
            {"version_id": version_id, "run_id": run_id},
        )
    command.downgrade(config, "0017_exercise_content_snapshots")
    assert "current_exercise_version_id" not in {
        column["name"] for column in inspect(engine).get_columns("assessment_runs")
    }
    with engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT exercise_version_id FROM assessment_run_version_downgrade "
                "WHERE assessment_run_id = :run_id"
            ),
            {"run_id": run_id},
        ) == version_id

    command.upgrade(config, "0018_assessment_run_exercise_version")
    assert "assessment_run_version_downgrade" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT current_exercise_version_id FROM assessment_runs WHERE id = :run_id"),
            {"run_id": run_id},
        ) == version_id
    engine.dispose()


def test_exercise_snapshot_migration_backfills_only_existing_v1_versions(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'snapshot-backfill.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0015_exercise_hint_ladder")
    engine = create_engine(url)
    user_id = uuid4().hex
    run_id = uuid4().hex
    known_response_id = uuid4().hex
    unknown_response_id = uuid4().hex
    known_attempt_id = uuid4().hex
    unknown_attempt_id = uuid4().hex
    version_id = uuid4().hex
    unknown_version_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": user_id, "email": "backfill@example.com", "password": "sentinel"},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions "
                "(id, exercise_id, version, lesson_id) "
                "VALUES (:id, 'variables-v1', 1, 'variables-v1')"
            ),
            {"id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions "
                "(id, exercise_id, version, lesson_id) "
                "VALUES (:id, 'variables-v1', 2, 'variables-v1')"
            ),
            {"id": unknown_version_id},
        )
        connection.execute(
            text(
                "INSERT INTO assessment_runs "
                "(id, user_id, status, asked_question_ids) "
                "VALUES (:id, :user_id, 'completed', '[]')"
            ),
            {"id": run_id, "user_id": user_id},
        )
        for response_id, question_id in (
            (known_response_id, "variables-v1"),
            (unknown_response_id, "published-later-v1"),
        ):
            connection.execute(
                text(
                    "INSERT INTO assessment_responses "
                    "(id, run_id, question_id, skill_id, difficulty, answer, is_correct) "
                    "VALUES (:id, :run_id, :question_id, 'python.variables', 0.1, 'x', 0)"
                ),
                {"id": response_id, "run_id": run_id, "question_id": question_id},
            )
        for attempt_id, lesson_id in (
            (known_attempt_id, "variables-v1"),
            (unknown_attempt_id, "published-later-v1"),
        ):
            connection.execute(
                text(
                    "INSERT INTO knowledge_check_attempts "
                    "(id, user_id, lesson_id, skill_id, score, passed) "
                    "VALUES (:id, :user_id, :lesson_id, 'python.variables', 0, 0)"
                ),
                {"id": attempt_id, "user_id": user_id, "lesson_id": lesson_id},
            )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT exercise_version_id FROM assessment_responses WHERE id = :id"),
            {"id": known_response_id},
        ) == version_id
        assert connection.scalar(
            text("SELECT exercise_version_id FROM assessment_responses WHERE id = :id"),
            {"id": unknown_response_id},
        ) is None
        assert connection.scalar(
            text("SELECT exercise_version_id FROM knowledge_check_attempts WHERE id = :id"),
            {"id": known_attempt_id},
        ) == version_id
        assert connection.scalar(
            text("SELECT exercise_version_id FROM knowledge_check_attempts WHERE id = :id"),
            {"id": unknown_attempt_id},
        ) is None
        assert connection.scalar(
            text("SELECT content_snapshot FROM exercise_versions WHERE id = :id"),
            {"id": unknown_version_id},
        ) is None
    engine.dispose()


def test_exercise_snapshot_migration_roundtrip_keeps_global_hint_key_unique(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'snapshot-idempotency.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0015_exercise_hint_ladder")
    engine = create_engine(url)
    user_id = uuid4().hex
    version_ids = [uuid4().hex, uuid4().hex]
    hint_ids = [uuid4().hex, uuid4().hex]
    reveal_ids = [uuid4().hex, uuid4().hex]
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": user_id, "email": "idempotency@example.com", "password": "sentinel"},
        )
        for version_id, hint_id in zip(version_ids, hint_ids):
            connection.execute(
                text(
                    "INSERT INTO exercise_versions (id, exercise_id, version, lesson_id) "
                    "VALUES (:id, :exercise_id, 1, :lesson_id)"
                ),
                {"id": version_id, "exercise_id": version_id, "lesson_id": version_id},
            )
            connection.execute(
                text(
                    "INSERT INTO exercise_hints "
                    "(id, exercise_version_id, level, kind, content) "
                    "VALUES (:id, :version_id, 1, 'direction', 'hint')"
                ),
                {"id": hint_id, "version_id": version_id},
            )

    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO hint_reveals "
                "(id, user_id, exercise_version_id, hint_id, level, idempotency_key) "
                "VALUES (:id, :user_id, :version_id, :hint_id, 1, 'same-raw-key')"
            ),
            {
                "id": reveal_ids[0],
                "user_id": user_id,
                "version_id": version_ids[0],
                "hint_id": hint_ids[0],
            },
        )
        connection.execute(
            text(
                "INSERT INTO hint_reveals "
                "(id, user_id, exercise_version_id, hint_id, level, idempotency_key) "
                "VALUES (:id, :user_id, :version_id, :hint_id, 1, :key)"
            ),
            {
                "id": reveal_ids[1],
                "user_id": user_id,
                "version_id": version_ids[1],
                "hint_id": hint_ids[1],
                "key": _persisted_idempotency_key(UUID(version_ids[1]), "same-raw-key"),
            },
        )
    command.downgrade(config, "0015_exercise_hint_ladder")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT count(*) FROM hint_reveals WHERE user_id = :id"),
            {"id": user_id},
        ) == 2
        assert connection.scalar(
            text("SELECT idempotency_key FROM hint_reveals WHERE id = :id"),
            {"id": reveal_ids[0]},
        ) == "same-raw-key"
        assert connection.scalar(
            text("SELECT count(*) FROM hint_reveals WHERE idempotency_key = 'same-raw-key'"),
        ) == 1
        assert connection.scalar(
            text("SELECT count(*) FROM users WHERE email = 'idempotency@example.com'")
        ) == 1
    engine.dispose()


def test_published_exercise_version_delete_is_restricted_and_preserves_reveal(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'append-only-boundary.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    user_id = uuid4().hex
    version_id = uuid4().hex
    hint_id = uuid4().hex
    reveal_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": user_id, "email": "append-only@example.com", "password": "sentinel"},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions (id, exercise_id, version, lesson_id) "
                "VALUES (:id, 'variables-v1', 1, 'variables-v1')"
            ),
            {"id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_hints "
                "(id, exercise_version_id, level, kind, content) "
                "VALUES (:id, :version_id, 1, 'direction', 'hint')"
            ),
            {"id": hint_id, "version_id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO hint_reveals "
                "(id, user_id, exercise_version_id, hint_id, level, idempotency_key) "
                "VALUES (:id, :user_id, :version_id, :hint_id, 1, 'append-only-key')"
            ),
            {
                "id": reveal_id,
                "user_id": user_id,
                "version_id": version_id,
                "hint_id": hint_id,
            },
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys = ON"))
            connection.execute(
                text("DELETE FROM exercise_versions WHERE id = :id"),
                {"id": version_id},
            )

    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT count(*) FROM exercise_versions WHERE id = :id"),
            {"id": version_id},
        ) == 1
        assert connection.scalar(
            text("SELECT count(*) FROM hint_reveals WHERE id = :id"),
            {"id": reveal_id},
        ) == 1
    engine.dispose()


def test_0018_head_0018_head_keeps_sentinel_and_reveal(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'append-only-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "0018_assessment_run_exercise_version")
    engine = create_engine(url)
    user_id = uuid4().hex
    version_id = uuid4().hex
    hint_id = uuid4().hex
    reveal_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password)"),
            {"id": user_id, "email": "roundtrip-sentinel@example.com", "password": "sentinel"},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions (id, exercise_id, version, lesson_id) "
                "VALUES (:id, 'variables-v1', 1, 'variables-v1')"
            ),
            {"id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_hints "
                "(id, exercise_version_id, level, kind, content) "
                "VALUES (:id, :version_id, 1, 'direction', 'roundtrip hint')"
            ),
            {"id": hint_id, "version_id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO hint_reveals "
                "(id, user_id, exercise_version_id, hint_id, level, idempotency_key) "
                "VALUES (:id, :user_id, :version_id, :hint_id, 1, 'roundtrip-key')"
            ),
            {
                "id": reveal_id,
                "user_id": user_id,
                "version_id": version_id,
                "hint_id": hint_id,
            },
        )

    command.upgrade(config, "head")
    command.downgrade(config, "0018_assessment_run_exercise_version")
    command.upgrade(config, "head")

    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT email FROM users WHERE id = :id"),
            {"id": user_id},
        ) == "roundtrip-sentinel@example.com"
        assert connection.scalar(
            text("SELECT count(*) FROM hint_reveals WHERE id = :id"),
            {"id": reveal_id},
        ) == 1
    engine.dispose()
