"""Prove auth and version-bound learning facts survive new revision rollback."""
import os
import sys
from pathlib import Path
from uuid import UUID
sys.path.insert(0,str(Path(__file__).parents[1]/"apps"/"api"))
from sqlalchemy import create_engine, select, delete, text
from sqlalchemy.orm import Session
from app.db.models import User, LessonCompletion, ExerciseVersion
from app.exercise_hints import _seed_exercise

SENTINEL=UUID("c742873ea1e14952a848f8440ac52141")
engine=create_engine(os.environ["DATABASE_URL"])
with Session(engine) as db:
    if engine.dialect.name!="postgresql":
        raise SystemExit("Migration proof requires PostgreSQL")
    print("dialect=postgresql database="+str(db.scalar(text("SELECT current_database()"))))
    if sys.argv[1]=="create":
        db.add(User(id=SENTINEL,email="migration-sentinel@example.invalid",password_hash="unusable-test-only"))
        db.flush()
        version=_seed_exercise(db,"variables-v1",seed_hints=False)
        db.add(LessonCompletion(user_id=SENTINEL,lesson_id="variables-v1",answer="6",exercise_version_id=version.id,evidence_type="authored_quiz_correct"))
    else:
        user=db.get(User,SENTINEL)
        completion=db.get(LessonCompletion,(SENTINEL,"variables-v1"))
        version=db.get(ExerciseVersion,completion.exercise_version_id) if completion else None
        if (user is None or user.password_hash!="unusable-test-only" or completion is None or completion.answer!="6"
            or version is None or version.content_snapshot["lesson"]["id"]!="variables-v1"):
            raise SystemExit("Migration sentinel was not preserved")
        db.execute(delete(LessonCompletion).where(LessonCompletion.user_id==SENTINEL))
        db.execute(delete(User).where(User.id==SENTINEL))
        print("auth and immutable learning sentinel preserved")
    db.commit()
