"""Prepare two experienced, disposable learners for the browser recovery test.

This is test setup, not an application entry point. It refuses every database
except the explicitly enabled, dedicated browser-CI SQLite file.
"""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.models import Goal, LessonCompletion, Profile, User
from app.db.session import engine
from app.learning import CODING_INTERFACE_SKILLS, _persisted_lesson_version, coding_practice_ready
from app.learning_content import LESSONS
from app.security import hash_password


def main():
    url = make_url(os.environ.get("DATABASE_URL", ""))
    if (os.environ.get("RUN_BROWSER_FIXTURES") != "1"
            or os.environ.get("APP_ENV") != "development"
            or url.get_backend_name() != "sqlite"
            or not url.database
            or Path(url.database).name != "mentor-browser-ci.sqlite3"):
        raise SystemExit("Recovery fixture requires an explicitly enabled disposable browser CI database")
    with Session(engine) as db:
        for viewport in ("desktop", "mobile"):
            email = f"browser-recovery-{viewport}@example.invalid"
            if db.scalar(select(User.id).where(User.email == email)) is not None:
                raise SystemExit("Recovery fixture already exists; start with a fresh browser CI database")
            user = User(email=email, password_hash=hash_password("Only-Disposable-CI-Account-2026"))
            db.add(user)
            db.flush()
            db.add_all([
                Profile(user_id=user.id, display_name="Тест восстановления", experience_level="junior", onboarding_completed=True),
                Goal(user_id=user.id, target_role="Python Backend", weekly_minutes=180),
            ])
            # Trusted test fixtures have exact immutable primary completions;
            # no forged mastery score and no production bypass route are used.
            for skill_id in sorted(CODING_INTERFACE_SKILLS):
                lesson = next(item for item in LESSONS if item["skill_id"] == skill_id)
                version = _persisted_lesson_version(lesson["id"], db)
                db.add(LessonCompletion(user_id=user.id, lesson_id=lesson["id"],
                    exercise_version_id=version.id, answer="Disposable browser setup completion"))
            db.flush()
            assert coding_practice_ready(db, user)
        db.commit()
    print("Two disposable coding-recovery learners prepared")


if __name__ == "__main__":
    main()
