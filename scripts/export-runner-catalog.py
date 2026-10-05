"""Export reviewed authored cases for the private execution host (not a web asset).

Run from repository root: PYTHONPATH=apps/api python scripts/export-runner-catalog.py /path/catalog.json
Deploy this immutable file with the pinned image and reviewed policy. It contains
hidden expected values and must never be served from web/static/public storage.
"""
import json
import sys
from pathlib import Path
from app.runner_exercise_content import RUNNER_EXERCISES

rows = [{"exercise_id": row["exercise_id"], "version": row["version"],
         "cases": [{key: case[key] for key in ("args", "kwargs", "expected", "visibility")} for case in row["cases"]]}
        for row in RUNNER_EXERCISES.values()]
destination = Path(sys.argv[1])
destination.write_text(json.dumps(rows, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
destination.chmod(0o600)
print(f"exported {len(rows)} immutable coding exercises")
