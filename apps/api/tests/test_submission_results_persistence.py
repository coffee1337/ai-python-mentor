from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    CodingAttempt,
    SubmissionResult,
    SubmissionTestResult,
    User,
)
from app.db.session import get_db
from app.main import app
from test_auth import client


def test_submission_results_keep_test_visibility_and_enforce_idempotency(client):
    assert client.post(
        "/auth/register",
        json={"email": "submission-result@example.com", "password": "safe-password"},
    ).status_code == 201

    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User).where(User.email == "submission-result@example.com"))
        attempt = CodingAttempt(
            user_id=user.id,
            exercise_id="variables-v1",
            language="python",
            mode="function",
            source_code="unexecuted learner source",
            status="passed",
        )
        db.add(attempt)
        db.flush()

        result = SubmissionResult(
            coding_attempt_id=attempt.id,
            idempotency_key="opaque-result-key-1",
            protocol_version=1,
            status="failed",
            tests_passed=1,
            tests_total=2,
            test_results=[
                SubmissionTestResult(test_index=0, visibility="public", status="passed"),
                SubmissionTestResult(test_index=1, visibility="hidden", status="failed"),
            ],
        )
        db.add(result)
        db.commit()
        db.refresh(result)

        stored = db.scalar(
            select(SubmissionResult).where(
                SubmissionResult.coding_attempt_id == attempt.id
            )
        )
        assert stored.idempotency_key == "opaque-result-key-1"
        assert stored.exercise_version_id is None
        assert stored.skill_evidence is None
        assert [(item.test_index, item.visibility, item.status) for item in stored.test_results] == [
            (0, "public", "passed"),
            (1, "hidden", "failed"),
        ]
        # Test-result storage intentionally has no place for source, test names,
        # or raw per-test output; visibility can therefore govern later reads.
        forbidden_columns = {
            "source",
            "source_code",
            "test_source",
            "test_name",
            "output",
        }
        for model in (SubmissionResult, SubmissionTestResult):
            assert not forbidden_columns & set(model.__table__.columns.keys())
        assert not hasattr(stored.test_results[1], "source")

        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(
                SubmissionResult(
                    coding_attempt_id=attempt.id,
                    idempotency_key="another-key",
                    status="passed",
                )
            )
            db.flush()

        second_attempt = CodingAttempt(
            user_id=user.id,
            exercise_id="variables-v1",
            language="python",
            mode="function",
            source_code="also unexecuted",
            status="unavailable",
        )
        db.add(second_attempt)
        db.flush()
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(
                SubmissionResult(
                    coding_attempt_id=second_attempt.id,
                    idempotency_key="opaque-result-key-1",
                    status="unavailable",
                )
            )
            db.flush()

        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(
                SubmissionTestResult(
                    submission_result_id=stored.id,
                    test_index=2,
                    visibility="internal",
                    status="failed",
                )
            )
            db.flush()


def test_submission_results_migration_round_trip_preserves_old_attempts(
    tmp_path, monkeypatch
):
    url = f"sqlite:///{(tmp_path / 'submission-results.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))

    command.upgrade(config, "0028_correct_variables_data_types_mapping")
    engine = create_engine(url)
    user_id = uuid4().hex
    attempt_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash) "
                "VALUES (:id, 'submission-migration@example.com', 'sentinel-hash')"
            ),
            {"id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO coding_attempts "
                "(id, user_id, exercise_id, language, mode, source_code, status, result) "
                "VALUES (:id, :user_id, 'variables-v1', 'python', 'function', "
                "'legacy unexecuted source', 'unavailable', 'legacy result')"
            ),
            {"id": attempt_id, "user_id": user_id},
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        names = set(inspect(connection).get_table_names())
        assert {"submission_results", "submission_test_results"} <= names
        assert {"exercise_version_id"} <= {
            column["name"]
            for column in inspect(connection).get_columns("coding_attempts")
        }
        assert {"exercise_version_id"} <= {
            column["name"]
            for column in inspect(connection).get_columns("submission_results")
        }
        old_attempt = connection.execute(
            text(
                "SELECT source_code, status, result FROM coding_attempts WHERE id = :id"
            ),
            {"id": attempt_id},
        ).one()
        assert old_attempt == (
            "legacy unexecuted source",
            "unavailable",
            "legacy result",
        )
        assert connection.scalar(text("SELECT count(*) FROM submission_results")) == 0
        assert connection.scalar(text("SELECT count(*) FROM skill_evidence")) == 0

        result_id = uuid4().hex
        connection.execute(
            text(
                "INSERT INTO submission_results "
                "(id, coding_attempt_id, idempotency_key, status, tests_passed, tests_total) "
                "VALUES (:id, :attempt_id, 'migration-result-key', 'failed', 1, 2)"
            ),
            {"id": result_id, "attempt_id": attempt_id},
        )
        test_id = uuid4().hex
        connection.execute(
            text(
                "INSERT INTO submission_test_results "
                "(id, submission_result_id, test_index, visibility, status) "
                "VALUES (:id, :result_id, 0, 'hidden', 'failed')"
            ),
            {"id": test_id, "result_id": result_id},
        )
        assert connection.scalar(
            text(
                "SELECT visibility FROM submission_test_results WHERE id = :id"
            ),
            {"id": test_id},
        ) == "hidden"

    command.downgrade(config, "0028_correct_variables_data_types_mapping")
    with engine.connect() as connection:
        names = set(inspect(connection).get_table_names())
        assert "submission_results" not in names
        assert "submission_test_results" not in names
        assert connection.scalar(
            text("SELECT source_code FROM coding_attempts WHERE id = :id"),
            {"id": attempt_id},
        ) == "legacy unexecuted source"
        assert connection.scalar(
            text("SELECT email FROM users WHERE id = :id"),
            {"id": user_id},
        ) == "submission-migration@example.com"

    command.upgrade(config, "0029_submission_results")
    with engine.connect() as connection:
        assert "exercise_version_id" not in {
            column["name"]
            for column in inspect(connection).get_columns("coding_attempts")
        }
        assert "exercise_version_id" not in {
            column["name"]
            for column in inspect(connection).get_columns("submission_results")
        }

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT count(*) FROM coding_attempts WHERE id = :id"),
            {"id": attempt_id},
        ) == 1
        # Upgrade never invents a verified result for a legacy CodingAttempt.
        assert connection.scalar(text("SELECT count(*) FROM submission_results")) == 0
    engine.dispose()


def test_version_bound_runner_data_blocks_unsafe_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'version-bound-downgrade.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))

    command.upgrade(config, "head")
    engine = create_engine(url)
    user_id = uuid4().hex
    version_id = uuid4().hex
    attempt_id = uuid4().hex
    result_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash) "
                "VALUES (:id, 'version-bound@example.com', 'sentinel-hash')"
            ),
            {"id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO exercise_versions "
                "(id, exercise_id, version) "
                "VALUES (:id, 'variables-v1', 1)"
            ),
            {"id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO coding_attempts "
                "(id, user_id, exercise_id, exercise_version_id, language, mode, "
                "source_code, status) VALUES "
                "(:id, :user_id, 'variables-v1', :version_id, 'python', "
                "'function', 'unexecuted', 'passed')"
            ),
            {"id": attempt_id, "user_id": user_id, "version_id": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO submission_results "
                "(id, coding_attempt_id, exercise_version_id, idempotency_key, "
                "status, tests_passed, tests_total) VALUES "
                "(:id, :attempt_id, :version_id, 'version-bound-key', "
                "'passed', 1, 1)"
            ),
            {
                "id": result_id,
                "attempt_id": attempt_id,
                "version_id": version_id,
            },
        )

    with pytest.raises(RuntimeError, match="version-bound"):
        command.downgrade(config, "0029_submission_results")

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0030_bind_submission_results_to_exercise_version"
        )
        assert connection.scalar(
            text(
                "SELECT exercise_version_id FROM submission_results "
                "WHERE id = :id"
            ),
            {"id": result_id},
        ) == version_id
        assert connection.scalar(
            text(
                "SELECT idempotency_key FROM submission_results "
                "WHERE id = :id"
            ),
            {"id": result_id},
        ) == "version-bound-key"
    engine.dispose()
