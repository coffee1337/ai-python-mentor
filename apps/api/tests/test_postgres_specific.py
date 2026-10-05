"""PostgreSQL-only checks for database semantics that SQLite cannot provide.

These tests deliberately do not use the shared ``client`` fixture: it creates
an in-memory SQLite database for the API suite.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    ExerciseVersion,
    Skill,
    SkillEvidence,
    SkillMasteryAudit,
    User,
    UserSkill,
)
from app.db.models import KnowledgeCheckAttempt
from app.skill_evidence import record_evidence
from app.skill_graph import seed_skill_graph


@dataclass(frozen=True)
class SandboxData:
    user_id: UUID
    skill_id: str
    exercise_id: str
    exercise_version_id: UUID


@pytest.fixture(scope="module")
def postgres_engine():
    """Use only an explicitly requested DATABASE_URL connection."""

    if os.getenv("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("PostgreSQL-specific tests require RUN_POSTGRES_TESTS=1")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL-specific tests require DATABASE_URL")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        dialect = connection.dialect.name
        driver = connection.dialect.driver
        if dialect == "postgresql":
            database = str(
                connection.execute(text("SELECT current_database()")).scalar_one()
            )
        elif dialect == "sqlite":
            row = connection.execute(text("PRAGMA database_list")).first()
            database = str(row[2] if row is not None and row[2] else ":memory:")
        else:
            database = str(engine.url.database or "<unknown>")

        proof = f"dialect={dialect} driver={driver} database={database}"
        # Deliberately print only server-reported identity, never DATABASE_URL.
        print(f"[postgres-specific] {proof}")
        if dialect != "postgresql":
            pytest.skip(f"PostgreSQL-specific tests skipped ({proof})")

    yield engine
    engine.dispose()


@pytest.fixture()
def sandbox(postgres_engine) -> SandboxData:
    """Create isolated rows and remove only those rows after the test."""

    session_factory = sessionmaker(
        bind=postgres_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    user_id = uuid4()
    skill_id = f"postgres-specific.{uuid4().hex}"
    exercise_version_id = uuid4()
    exercise_id = f"postgres-specific-{uuid4().hex}"
    snapshot = {
        "schema_version": 1,
        "exercise_id": exercise_id,
        "version": 1,
        "lesson": {"id": exercise_id, "skill_id": skill_id},
        "checks": [
            {
                "id": "postgres-specific-check",
                "prompt": "Is this a PostgreSQL test?",
                "choices": ["yes"],
                "answer": "yes",
                "explanation": "Test data only.",
            }
        ],
    }

    with session_factory() as db:
        # record_evidence calls seed_skill_graph itself. Seeding once before
        # concurrent workers keeps graph setup out of the lock race.
        seed_skill_graph(db)
        db.add_all(
            [
                Skill(
                    id=skill_id,
                    name="PostgreSQL test skill",
                    category="test",
                    difficulty=0.0,
                    importance=0.5,
                    tags=[],
                    description="Test-only skill",
                ),
                User(
                    id=user_id,
                    email=f"{uuid4().hex}@postgres-specific.invalid",
                    password_hash="test-only",
                ),
                ExerciseVersion(
                    id=exercise_version_id,
                    exercise_id=exercise_id,
                    version=1,
                    lesson_id=exercise_id,
                    content_snapshot=snapshot,
                ),
                UserSkill(
                    user_id=user_id,
                    skill_id=skill_id,
                    knowledge_score=0.0,
                    practice_score=0.0,
                    independent_score=0.0,
                    retention_score=0.0,
                    confidence=0.0,
                    mastery_weight=0.0,
                    evidence_count=0,
                ),
            ]
        )
        db.commit()

    data = SandboxData(
        user_id=user_id,
        skill_id=skill_id,
        exercise_id=exercise_id,
        exercise_version_id=exercise_version_id,
    )
    try:
        yield data
    finally:
        with session_factory() as db:
            db.execute(delete(User).where(User.id == data.user_id))
            db.execute(
                delete(ExerciseVersion).where(
                    ExerciseVersion.id == data.exercise_version_id
                )
            )
            db.execute(delete(Skill).where(Skill.id == data.skill_id))
            db.commit()


def _record_one_evidence(
    engine,
    *,
    user_id: UUID,
    skill_id: str,
    source_id: UUID,
    start: Barrier,
) -> None:
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    with session_factory() as db:
        try:
            start.wait(timeout=15)
            record_evidence(
                db,
                user_id=user_id,
                skill_id=skill_id,
                source_type="knowledge_check_attempt",
                source_id=str(source_id),
                result_score=1.0,
                assisted=False,
                hint_count=0,
                occurred_at=datetime.now(timezone.utc),
            )
            db.commit()
        except BaseException:
            db.rollback()
            raise


def test_parallel_skill_evidence_updates_are_serialized(
    postgres_engine, sandbox: SandboxData
):
    session_factory = sessionmaker(
        bind=postgres_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    source_ids = (uuid4(), uuid4())
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add_all(
            [
                KnowledgeCheckAttempt(
                    id=source_id,
                    user_id=sandbox.user_id,
                    exercise_version_id=sandbox.exercise_version_id,
                    lesson_id=sandbox.exercise_id,
                    skill_id=sandbox.skill_id,
                    score=1.0,
                    passed=True,
                    created_at=now,
                )
                for source_id in source_ids
            ]
        )
        db.commit()

    start = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _record_one_evidence,
                postgres_engine,
                user_id=sandbox.user_id,
                skill_id=sandbox.skill_id,
                source_id=source_id,
                start=start,
            )
            for source_id in source_ids
        ]
        for future in futures:
            future.result(timeout=30)

    with session_factory() as db:
        mastery = db.scalar(
            select(UserSkill).where(
                UserSkill.user_id == sandbox.user_id,
                UserSkill.skill_id == sandbox.skill_id,
            )
        )
        evidence_count = db.scalar(
            select(func.count())
            .select_from(SkillEvidence)
            .where(
                SkillEvidence.user_id == sandbox.user_id,
                SkillEvidence.skill_id == sandbox.skill_id,
            )
        )

    assert mastery is not None
    assert evidence_count == 2
    assert mastery.evidence_count == 2
    assert mastery.mastery_weight == pytest.approx(2.0)
    assert mastery.knowledge_score == pytest.approx(1.0)


def test_skill_evidence_idempotency_unique_constraint_rejects_duplicate(
    postgres_engine, sandbox: SandboxData
):
    session_factory = sessionmaker(
        bind=postgres_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    idempotency_key = f"postgres-specific:{uuid4().hex}"
    common = {
        "user_id": sandbox.user_id,
        "skill_id": sandbox.skill_id,
        "source_type": "assessment_response",
        "result_score": 1.0,
        "assisted": False,
        "hint_count": 0,
        "occurred_at": datetime.now(timezone.utc),
        "idempotency_key": idempotency_key,
    }

    with session_factory() as db:
        db.add(SkillEvidence(id=uuid4(), source_id="first", **common))
        db.commit()

        db.add(SkillEvidence(id=uuid4(), source_id="duplicate", **common))
        with pytest.raises(IntegrityError) as error:
            db.commit()
        db.rollback()

    constraint_name = getattr(getattr(error.value.orig, "diag", None), "constraint_name", None)
    assert constraint_name == "uq_skill_evidence_idempotency"


def test_user_delete_cascades_learning_children(
    postgres_engine, sandbox: SandboxData
):
    session_factory = sessionmaker(
        bind=postgres_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    with session_factory() as db:
        evidence = SkillEvidence(
            user_id=sandbox.user_id,
            skill_id=sandbox.skill_id,
            source_type="assessment_response",
            source_id=str(uuid4()),
            result_score=1.0,
            assisted=False,
            hint_count=0,
            occurred_at=datetime.now(timezone.utc),
            idempotency_key=f"postgres-specific:{uuid4().hex}",
        )
        db.add(evidence)
        db.flush()
        db.add(
            SkillMasteryAudit(
                evidence_id=evidence.id,
                user_id=sandbox.user_id,
                skill_id=sandbox.skill_id,
                before_mastery=0.0,
                after_mastery=1.0,
                before_evidence_count=0,
                after_evidence_count=1,
                policy_version="test",
            )
        )
        db.commit()

        db.execute(delete(User).where(User.id == sandbox.user_id))
        db.commit()

    with session_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(SkillEvidence)
                .where(SkillEvidence.user_id == sandbox.user_id)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(UserSkill)
                .where(UserSkill.user_id == sandbox.user_id)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(SkillMasteryAudit)
                .where(SkillMasteryAudit.user_id == sandbox.user_id)
            )
            == 0
        )
