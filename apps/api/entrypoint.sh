#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
deadline = time.time() + 90
while time.time() < deadline:
    try:
        with create_engine(url, pool_pre_ping=True).connect() as connection:
            connection.execute(text("SELECT 1"))
        break
    except Exception:  # Do not print connection strings or driver exceptions.
        time.sleep(2)
else:
    sys.exit("Database is not ready")
PY

if [ "${APPLY_MIGRATIONS:-false}" = "true" ]; then
  echo "Applying explicitly enabled migrations..."
  alembic upgrade head
fi

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${API_WORKERS:-2}" --no-access-log
