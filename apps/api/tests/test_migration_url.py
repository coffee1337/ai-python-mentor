"""Real Alembic entry point must preserve percent signs in DATABASE_URL."""
import os
from pathlib import Path
import subprocess
import sys


def test_alembic_preserves_literal_percent_in_database_path(tmp_path):
    database = tmp_path / "native 100% database.sqlite3"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"},
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert database.is_file()
