"""Verify that the deployed database carries the authored content.

Runs after migrations as a one-shot compose step: it fails the deployment when
90 skills or 90 coding exercises are missing, instead of serving an empty course.
"""
from __future__ import annotations

import sys

from sqlalchemy import func, select, text

from app.db.models import Skill
from app.db.session import SessionLocal
from app.runner_exercise_content import RUNNER_EXERCISES

EXPECTED_LESSONS = 90
EXPECTED_EXERCISES = 90


def main() -> int:
    problems: list[str] = []
    with SessionLocal() as db:
        skills = db.scalar(select(func.count()).select_from(Skill)) or 0
        if skills < EXPECTED_LESSONS:
            problems.append(f"skills={skills} expected>={EXPECTED_LESSONS}")
        lessons = db.execute(text("SELECT count(*) FROM lesson_completions")).scalar_one()
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        exercises = len(RUNNER_EXERCISES)
        if exercises != EXPECTED_EXERCISES:
            problems.append(f"coding_exercises={exercises} expected={EXPECTED_EXERCISES}")
        chunks = db.execute(text("SELECT count(*) FROM knowledge_chunks")).scalar_one()
    if problems:
        print("seed_check=failed " + " ".join(problems), file=sys.stderr)
        return 1
    print(f"seed_check=ok skills={skills} exercises={exercises} knowledge_chunks={chunks} "
          f"lesson_completions={lessons} revision={revision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
