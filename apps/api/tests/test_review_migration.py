import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_review_schema_roundtrip_preserves_review_rows_and_existing_user(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'review-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))

    command.upgrade(config, "head")
    engine = create_engine(url)
    user_id = uuid4().hex
    evidence_id = uuid4().hex
    audit_id = uuid4().hex
    session_id = uuid4().hex
    attempt_id = uuid4().hex
    version_id = uuid4().hex
    now = datetime.now(timezone.utc)
    review_day = now.date().isoformat()

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) "
                    "VALUES (:id, :email, :password_hash)"
                ),
                {
                    "id": user_id,
                    "email": "review-roundtrip@example.com",
                    "password_hash": "sentinel",
                },
            )
            connection.execute(
                text(
                    "UPDATE skills SET name = 'Variables', category = 'python', "
                    "description = 'sentinel' WHERE id = 'python.variables'"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO exercise_versions "
                    "(id, exercise_id, version, lesson_id, content_snapshot) "
                    "VALUES (:id, 'variables-v1', 1, 'variables-v1', :snapshot)"
                ),
                {
                    "id": version_id,
                    "snapshot": json.dumps(
                        {
                            "lesson": {
                                "id": "variables-v1",
                                "skill_id": "python.variables",
                                "prompt": "p",
                                "choices": ["a"],
                                "answer": "a",
                            }
                        }
                    ),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO skill_evidence "
                    "(id, user_id, skill_id, source_type, source_id, retention_only, "
                    "result_score, assisted, hint_count, occurred_at, idempotency_key, metadata) "
                    "VALUES (:id, :user_id, 'python.variables', 'review_attempt', :source_id, "
                    "1, 1.0, 0, 0, :occurred_at, :idempotency_key, :metadata)"
                ),
                {
                    "id": evidence_id,
                    "user_id": user_id,
                    "source_id": attempt_id,
                    "occurred_at": now,
                    "idempotency_key": "sha256:roundtrip-evidence",
                    "metadata": json.dumps(
                        {
                            "review_policy": {
                                "version": "review-v1",
                                "schedule_applied": True,
                            }
                        }
                    ),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO skill_mastery_audit "
                    "(id, evidence_id, user_id, skill_id, before_mastery, after_mastery, "
                    "before_evidence_count, after_evidence_count, policy_version) "
                    "VALUES (:id, :evidence_id, :user_id, 'python.variables', "
                    "0.5, 0.5, 1, 1, 'review-v1')"
                ),
                {
                    "id": audit_id,
                    "evidence_id": evidence_id,
                    "user_id": user_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO review_sessions "
                    "(id, user_id, skill_id, exercise_version_id, scheduled_for, "
                    "completed_at, token_hash) "
                    "VALUES (:id, :user_id, 'python.variables', :version_id, "
                    ":scheduled_for, :completed_at, :token_hash)"
                ),
                {
                    "id": session_id,
                    "user_id": user_id,
                    "version_id": version_id,
                    "scheduled_for": review_day,
                    "completed_at": now,
                    "token_hash": "a" * 64,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO review_attempts "
                    "(id, review_session_id, user_id, skill_id, exercise_version_id, "
                    "skill_evidence_id, evidence_source_type, scheduled_for, applied_on, "
                    "idempotency_key, occurred_at, answers) "
                    "VALUES (:id, :session_id, :user_id, 'python.variables', :version_id, "
                    ":evidence_id, 'review_attempt', :scheduled_for, :applied_on, "
                    ":idempotency_key, :occurred_at, :answers)"
                ),
                {
                    "id": attempt_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "version_id": version_id,
                    "evidence_id": evidence_id,
                    "scheduled_for": review_day,
                    "applied_on": review_day,
                    "idempotency_key": "sha256:roundtrip-attempt",
                    "occurred_at": now,
                    "answers": json.dumps({"q": "a"}),
                },
            )

        command.downgrade(config, "0025_assessment_mistake_mappings")
        tables = set(inspect(engine).get_table_names())
        assert "review_sessions" not in tables
        assert "review_attempts" not in tables
        assert "review_scheduler_downgrade_evidence" in tables
        assert "review_scheduler_downgrade_attempts" in tables
        assert "review_api_downgrade_session_fields" in tables
        assert "review_api_downgrade_attempt_fields" in tables

        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM review_scheduler_downgrade_evidence "
                    "WHERE id = :id"
                ),
                {"id": evidence_id},
            ) == 1
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM review_scheduler_downgrade_attempts "
                    "WHERE id = :id"
                ),
                {"id": attempt_id},
            ) == 1
            assert connection.scalar(
                text(
                    "SELECT token_hash FROM review_api_downgrade_session_fields "
                    "WHERE id = :id"
                ),
                {"id": session_id},
            ) == "a" * 64
            assert connection.scalar(
                text(
                    "SELECT answers FROM review_api_downgrade_attempt_fields "
                    "WHERE id = :id"
                ),
                {"id": attempt_id},
            ) is not None

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT email FROM users WHERE id = :id"),
                {"id": user_id},
            ) == "review-roundtrip@example.com"
            assert connection.scalar(
                text("SELECT source_type FROM skill_evidence WHERE id = :id"),
                {"id": evidence_id},
            ) == "review_attempt"
            assert connection.scalar(
                text("SELECT retention_only FROM skill_evidence WHERE id = :id"),
                {"id": evidence_id},
            ) in (1, True)
            assert connection.scalar(
                text("SELECT token_hash FROM review_sessions WHERE id = :id"),
                {"id": session_id},
            ) == "a" * 64
            assert connection.scalar(
                text("SELECT answers FROM review_attempts WHERE id = :id"),
                {"id": attempt_id},
            ) is not None
    finally:
        engine.dispose()
