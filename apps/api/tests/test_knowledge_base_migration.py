"""Reversibility of the knowledge-chunk index against existing data."""
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_knowledge_chunk_migration_roundtrip_preserves_existing_data(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'kb-roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))

    command.upgrade(config, "head")
    engine = create_engine(url)
    user_id = uuid4().hex
    version_id = uuid4().hex
    chunk_id = uuid4().hex

    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO users (id, email, password_hash) "
                     "VALUES (:id, :email, 'sentinel')"),
                {"id": user_id, "email": "kb-roundtrip@example.com"},
            )
            connection.execute(
                text("UPDATE skills SET description = 'sentinel' "
                     "WHERE id = 'python.variables'"),
            )
            connection.execute(
                text("INSERT INTO exercise_versions "
                     "(id, exercise_id, version, lesson_id, content_snapshot) "
                     "VALUES (:id, 'variables-v1', 1, 'variables-v1', :snapshot)"),
                {"id": version_id,
                 "snapshot": json.dumps({"lesson": {"skill_id": "python.variables"}})},
            )
            connection.execute(
                text("INSERT INTO knowledge_chunks "
                     "(id, exercise_version_id, skill_id, section, ordinal, content, "
                     "content_digest, char_count, embedding, embedding_dim, embedding_model) "
                     "VALUES (:id, :vid, 'python.variables', 'body', 0, :content, "
                     "'sha256:sentinel', 12, :blob, 4, 'test-embed')"),
                {"id": chunk_id, "vid": version_id, "content": "sentinel body",
                 "blob": b"\x00\x00\x80\x3f\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"},
            )

        command.downgrade(config, "0030_bind_submission_results_to_exercise_version")
        assert "knowledge_chunks" not in set(inspect(engine).get_table_names())

        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT email FROM users WHERE id = :id"),
                {"id": user_id},
            ) == "kb-roundtrip@example.com"
            assert connection.scalar(
                text("SELECT description FROM skills WHERE id = 'python.variables'"),
            ) == "sentinel"
            assert connection.scalar(
                text("SELECT content_snapshot FROM exercise_versions WHERE id = :id"),
                {"id": version_id},
            ) is not None

        command.upgrade(config, "head")
        with engine.begin() as connection:
            # The derived index comes back empty; authored content is untouched.
            assert connection.scalar(text("SELECT count(*) FROM knowledge_chunks")) == 0
            assert connection.scalar(
                text("SELECT email FROM users WHERE id = :id"),
                {"id": user_id},
            ) == "kb-roundtrip@example.com"
            assert connection.scalar(
                text("SELECT description FROM skills WHERE id = 'python.variables'"),
            ) == "sentinel"
            assert connection.scalar(
                text("SELECT content_snapshot FROM exercise_versions WHERE id = :id"),
                {"id": version_id},
            ) is not None
    finally:
        engine.dispose()
