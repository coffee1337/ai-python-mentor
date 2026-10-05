#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
deadline = time.time() + 90
last = None
while time.time() < deadline:
    try:
        with create_engine(url, pool_pre_ping=True).connect() as connection:
            connection.execute(text("SELECT 1"))
        break
    except Exception as exc:  # noqa: BLE001 - startup probe
        last = exc
        time.sleep(2)
else:
    sys.exit(f"Database is not ready: {last}")
PY

echo "Applying migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
