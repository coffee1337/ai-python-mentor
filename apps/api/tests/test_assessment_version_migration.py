from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_0018_version_capacity_roundtrip(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'assessment-version.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))

    command.upgrade(config, "0017_exercise_content_snapshots")
    engine = create_engine(url)

    command.upgrade(config, "0018_assessment_run_exercise_version")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0018_assessment_run_exercise_version"
        )
    assert inspect(engine).get_columns("alembic_version")[0]["type"].length == 128

    command.downgrade(config, "0017_exercise_content_snapshots")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0017_exercise_content_snapshots"
        )
    assert inspect(engine).get_columns("alembic_version")[0]["type"].length == 128

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0037_lesson_reflections"
        )
    engine.dispose()
