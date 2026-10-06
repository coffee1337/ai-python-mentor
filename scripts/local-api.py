"""Native development entry point; called with the project's Python 3.12 venv."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"


def main() -> int:
    # A redirected legacy Windows console may not encode a Unicode project path.
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sqlite", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        print("Python 3.12 is required. Run scripts/start-api.ps1.", file=sys.stderr)
        return 1
    try:
        from dotenv import load_dotenv
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
    except ImportError:
        print("Dependencies are missing. Run start-api.ps1 without -SkipInstall.", file=sys.stderr)
        return 1

    # Only this backend process reads server secrets. Neither the calling shell
    # nor the frontend launcher receives them. Existing process settings win.
    load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
    if os.getenv("APP_ENV", "development").strip().casefold() != "development":
        print("This launcher is for development only. Check APP_ENV in your shell and .env.", file=sys.stderr)
        return 1
    os.environ["APP_ENV"] = "development"
    os.environ["COOKIE_SECURE"] = "false"  # Local HTTP, bound only to loopback.
    origins = [item.strip() for item in os.getenv("WEB_ORIGINS", "").split(",") if item.strip()]
    for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        if origin not in origins:
            origins.append(origin)
    os.environ["WEB_ORIGINS"] = ",".join(origins)
    os.chdir(API_ROOT)

    if args.use_sqlite:
        database_file = API_ROOT / "mentor-local.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{database_file.as_posix()}"
        print(f"SQLite selected explicitly: {database_file}", flush=True)
        print("Existing PostgreSQL accounts and history remain in PostgreSQL; they are not copied here.", flush=True)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("Set DATABASE_URL in your shell or root .env, or pass -UseSqlite for a local file database.", file=sys.stderr)
        return 1
    try:
        url = make_url(database_url)
        dialect = url.get_backend_name()
        if dialect not in {"sqlite", "postgresql"}:
            raise ValueError()
        connect_args = {"connect_timeout": 5} if dialect == "postgresql" else {}
        engine = create_engine(url, connect_args=connect_args)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except Exception:
        # Driver exceptions can contain credentials; keep them out of diagnostics.
        print("Database check failed. API was not started; no fallback database was selected.", file=sys.stderr)
        print("For PostgreSQL: check DATABASE_URL, run Get-Service *postgres*, and check the server's port.", file=sys.stderr)
        print("For SQLite: check the database path and file permissions. See README.md.", file=sys.stderr)
        return 1

    print("Database connection OK. Applying migrations with the same configuration as the API...", flush=True)
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_ROOT)
    if result.returncode:
        print("Migrations failed. API was not started. Keep the database and fix the reported migration error.", file=sys.stderr)
        return result.returncode
    if args.prepare_only:
        print("API environment and schema are ready.", flush=True)
        return 0
    print("API: http://127.0.0.1:8000/docs (Ctrl+C to stop). Start scripts/start-web.ps1 in another terminal.", flush=True)
    try:
        return subprocess.run([
            sys.executable, "-m", "uvicorn", "app.main:app", "--reload",
            "--host", "127.0.0.1", "--port", "8000",
        ], cwd=API_ROOT).returncode
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
