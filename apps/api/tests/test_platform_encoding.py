"""UTF-8 assets must survive a legacy Windows default text encoding."""
import json
from pathlib import Path
import runpy
import sys
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ExerciseVersion, LessonCompletion, Skill, User
from app.db.session import get_db
from app.main import app

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
MIGRATION = API_ROOT / "migrations" / "versions" / "0036_content_completion.py"
SEEDS = API_ROOT / "migrations" / "data" / "0036_content_completion.json"


@pytest.fixture
def legacy_locale(monkeypatch):
    """Model cp1251 at file I/O, including when Python uses 'locale'."""
    original_open = Path.open

    def legacy_open(self, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        if "b" not in mode and encoding in (None, "locale"):
            encoding = "cp1251"
        return original_open(self, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", legacy_open)


def enforce_foreign_keys(engine):
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
    return engine


@pytest.fixture
def migration_foreign_keys(monkeypatch):
    original_factory = sa.engine_from_config
    def foreign_key_engine(*args, **kwargs):
        return enforce_foreign_keys(original_factory(*args, **kwargs))
    monkeypatch.setattr(sa, "engine_from_config", foreign_key_engine)


def test_frozen_migration_seeds_decode_independently_of_windows_locale(legacy_locale):
    expected = json.loads(SEEDS.read_bytes())
    assert "Ответ на" in expected["mappings"][0]["error_text"]
    assert runpy.run_path(str(MIGRATION))["seeds"]() == expected


def test_locale_independent_upgrade_rollback_preserves_data_and_registration(tmp_path, monkeypatch, legacy_locale, migration_foreign_keys):
    url = f"sqlite:///{(tmp_path / 'windows-upgrade.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    command.upgrade(config, "0030_bind_submission_results_to_exercise_version")
    engine = enforce_foreign_keys(create_engine(url, connect_args={"check_same_thread": False}))
    user_id, version_id = uuid4(), uuid4()
    snapshot = {"schema_version": 1, "exercise_id": "encoding-sentinel", "version": 1,
                "lesson": {"id": "encoding-sentinel", "skill_id": "python.variables", "title": "Сохранённый урок 🙂"}}
    with Session(engine) as db:
        db.add_all([User(id=user_id, email="encoding-sentinel@example.invalid", password_hash="sentinel"),
                    ExerciseVersion(id=version_id, exercise_id="encoding-sentinel", version=1,
                                    lesson_id="encoding-sentinel", content_snapshot=snapshot)])
        db.flush()
        db.add(LessonCompletion(user_id=user_id, lesson_id="encoding-sentinel", answer="6",
                               exercise_version_id=version_id, evidence_type="authored_quiz_correct"))
        db.commit()

    def assert_preserved():
        with Session(engine) as db:
            assert db.get(User, user_id).password_hash == "sentinel"
            assert db.get(ExerciseVersion, version_id).content_snapshot == snapshot
            completion = db.get(LessonCompletion, (user_id, "encoding-sentinel"))
            assert completion.exercise_version_id == version_id and completion.answer == "6"

    factory = sessionmaker(bind=engine)
    def override_db():
        with factory() as db:
            yield db
    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    try:
        command.upgrade(config, "head")
        command.check(config)
        assert_preserved()
        with TestClient(app) as client:
            assert client.get("/ready").status_code == 200
            assert client.post("/auth/register", json={"email": "encoding-new@example.invalid", "password": "safe-password"}).status_code == 201
            command.downgrade(config, "0035_execution_jobs")
            assert_preserved()
            command.upgrade(config, "head")
            assert_preserved()
            assert client.get("/ready").status_code == 200
            assert client.get("/me").json()["email"] == "encoding-new@example.invalid"
    finally:
        engine.dispose()


def test_clean_upgrade_seeds_missing_skills_without_overwriting_existing_catalog(tmp_path, monkeypatch, migration_foreign_keys):
    url = f"sqlite:///{(tmp_path / 'foreign-keys.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    command.upgrade(config, "0035_execution_jobs")
    engine = enforce_foreign_keys(create_engine(url))
    with Session(engine) as db:
        assert db.get(Skill, "python.imports") is None
        existing = db.get(Skill, "python.variables")
        existing.name = "Историческое название 🙂"
        existing.description = "Сохранённое описание"
        db.commit()
    try:
        command.upgrade(config, "head")
        with Session(engine) as db:
            assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []
            assert db.get(Skill, "python.imports").name == "imports"
            assert db.get(Skill, "python.variables").name == "Историческое название 🙂"
            assert db.get(Skill, "python.variables").description == "Сохранённое описание"
        command.downgrade(config, "0035_execution_jobs")
        with Session(engine) as db:
            assert db.get(Skill, "python.imports") is not None
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as db:
            assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []
            assert db.get(Skill, "python.variables").name == "Историческое название 🙂"
    finally:
        engine.dispose()


def test_runner_catalog_export_is_utf8_under_legacy_locale(tmp_path, monkeypatch, legacy_locale):
    from app.runner_exercise_content import RUNNER_EXERCISES
    destination = tmp_path / "catalog.json"
    monkeypatch.setattr(sys, "argv", ["export-runner-catalog.py", str(destination)])
    runpy.run_path(str(REPO_ROOT / "scripts" / "export-runner-catalog.py"), run_name="__main__")
    catalog = json.loads(destination.read_bytes())
    assert len(catalog) == len(RUNNER_EXERCISES)
    for item in catalog:
        source = RUNNER_EXERCISES[item["exercise_id"]]
        assert item["cases"] == source["cases"]


def test_runner_client_reads_utf8_reviewed_policy_on_windows(tmp_path, monkeypatch, legacy_locale):
    from app.settings import load_runner_settings
    monkeypatch.setenv("RUNNER_URL", "https://runner.example/internal/v1/runner/executions")
    monkeypatch.setenv("RUNNER_AUTH_TOKEN", "test-only-token")
    for name in ("RUNNER_CA_FILE", "RUNNER_CLIENT_CERT_FILE", "RUNNER_CLIENT_KEY_FILE"):
        path = tmp_path / name
        path.write_bytes(b"test-only-placeholder")
        monkeypatch.setenv(name, str(path))
    policy_file = tmp_path / "policy.json"
    policy_file.write_bytes(json.dumps({"policy": "python-authored-v1", "isolation_verified": True,
                                       "review_note": "Проверено 🙂"}, ensure_ascii=False).encode("utf-8"))
    monkeypatch.setenv("RUNNER_VERIFIED_POLICY_FILE", str(policy_file))
    assert load_runner_settings().client_cert_file == str(tmp_path / "RUNNER_CLIENT_CERT_FILE")
