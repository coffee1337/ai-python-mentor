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


def test_parallel_ai_requests_claim_one_durable_lease(postgres_engine, sandbox):
    from app.ai_admission import reserve_ai_call
    from app.ai_gateway import GatewayError
    from app.db.domain_models import AICallReservation
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    start = Barrier(2)
    def claim():
        with factory() as db:
            start.wait(timeout=15)
            try:
                reserve_ai_call(db, sandbox.user_id, "postgres_test", "same-request",
                                limit=10, window_seconds=60, input_chars=1)
                return 200
            except GatewayError as error:
                return error.status
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(claim) for _ in range(2)]
        statuses = [future.result(timeout=30) for future in futures]
    assert sorted(statuses) == [200, 409]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AICallReservation).where(
            AICallReservation.user_id == sandbox.user_id)) == 1


def test_parallel_auth_admission_does_not_reset_counter(postgres_engine, sandbox):
    from fastapi import HTTPException
    from app.account_services import throttle, throttle_key
    from app.db.account_models import AuthThrottle
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    subject, start = str(sandbox.user_id), Barrier(4)
    def claim():
        with factory() as db:
            start.wait(timeout=15)
            try:
                throttle(db, scope="postgres_test", subject=subject, limit=1)
                return 200
            except HTTPException as error:
                return error.status_code
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(claim) for _ in range(4)]
            statuses = [future.result(timeout=30) for future in futures]
        assert sorted(statuses) == [200, 429, 429, 429]
        with factory() as db:
            row = db.get(AuthThrottle, throttle_key("postgres_test", subject))
            assert row.attempts == 4
    finally:
        with factory() as db:
            db.execute(delete(AuthThrottle).where(AuthThrottle.key == throttle_key("postgres_test", subject)))
            db.commit()


def test_parallel_account_token_consumption_is_single_use(postgres_engine, sandbox):
    from fastapi import HTTPException
    from app.account_services import consume_token, issue_token
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with factory() as db:
        token, _ = issue_token(db, sandbox.user_id, "email_verify", 15)
        db.commit()
    start = Barrier(2)
    def consume():
        with factory() as db:
            start.wait(timeout=15)
            try:
                user = consume_token(db, token, "email_verify")
                user.email_verified = True
                db.commit()
                return 200
            except HTTPException as error:
                db.rollback()
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(consume) for _ in range(2)]
        statuses = [future.result(timeout=30) for future in futures]
    assert sorted(statuses) == [200, 400]


def test_progress_calendar_uses_device_offset_not_postgres_connection_timezone(postgres_engine, sandbox):
    """Exercise the actual timestamptz + interval day aggregation on PostgreSQL."""
    from app.study_progress import CourseView, _period_counts
    from datetime import date

    now = datetime(2026, 10, 6, 0, 30, tzinfo=timezone.utc)
    start = datetime(2026, 10, 4, 21, 0, tzinfo=timezone.utc)
    dates = [date(2026, 10, 5), date(2026, 10, 6)]
    with sessionmaker(bind=postgres_engine, autoflush=False)() as db:
        user = db.get(User, sandbox.user_id)
        db.add_all([
            KnowledgeCheckAttempt(user_id=user.id, exercise_version_id=sandbox.exercise_version_id,
                lesson_id=sandbox.exercise_id, skill_id=sandbox.skill_id, score=0.0, passed=False,
                created_at=datetime(2026, 10, 5, 20, 30, tzinfo=timezone.utc)),
            KnowledgeCheckAttempt(user_id=user.id, exercise_version_id=sandbox.exercise_version_id,
                lesson_id=sandbox.exercise_id, skill_id=sandbox.skill_id, score=1.0, passed=True,
                created_at=datetime(2026, 10, 5, 21, 30, tzinfo=timezone.utc)),
            KnowledgeCheckAttempt(user_id=user.id, exercise_version_id=sandbox.exercise_version_id,
                lesson_id=sandbox.exercise_id, skill_id=sandbox.skill_id, score=1.0, passed=True,
                created_at=datetime(2026, 10, 6, 1, 0, tzinfo=timezone.utc)),
        ])
        db.flush()
        for connection_timezone in ("UTC", "Pacific/Honolulu"):
            db.execute(text(f"SET LOCAL TIME ZONE '{connection_timezone}'"))
            calendar = {day: {"date": day, "activity_count": 0, "lessons_completed": 0,
                "coding_submissions": 0, "acquisition_observations": 0,
                "independent_observations": 0, "assisted_observations": 0,
                "review_observations": 0} for day in dates}
            counts = _period_counts(db, user, start, now, 180, calendar)
            assert counts["active_days"] == 2
            assert counts["checks_attempted"] == 2 and counts["checks_passed"] == 1
            assert counts["acquisition_observations"] == counts["review_observations"] == 0
            assert [calendar[day]["activity_count"] for day in dates] == [1, 1]
            # Exact-publication tuple lookups and the same readiness projection
            # must also run on this dialect without generating lesson bindings.
            course = CourseView(db, user, now)
            assert len(course.lessons) == 90
            assert course.next is not None
        db.rollback()


def _prepare_study_owner(engine, user_id):
    from app.db.models import Profile
    from app.db.product_models import LearnerProject
    from app.projects import PROJECT_TEMPLATES

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(Profile(user_id=user_id, experience_level="beginner", onboarding_completed=True))
        template = PROJECT_TEMPLATES[0]
        project = LearnerProject(user_id=user_id, template_id=template["id"], template_snapshot=template)
        db.add(project)
        db.commit()
        return project.id, template["milestones"][0]["id"]


def test_postgres_draft_conflict_preserves_one_committed_variant(postgres_engine, sandbox):
    """Exercise the real route's owner lock, throttle and revision CAS together."""
    from fastapi import HTTPException, Response
    from app.db.study_draft_models import StudyDraft
    from app.study_drafts import DraftIdentity, SaveDraft, save_draft

    project_id, milestone = _prepare_study_owner(postgres_engine, sandbox.user_id)
    identity = DraftIdentity(kind="project_milestone", resource_id=str(project_id),
                             version=0, milestone_id=milestone)
    factory = sessionmaker(bind=postgres_engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        user = db.get(User, sandbox.user_id)
        initial = save_draft(SaveDraft(identity=identity, expected_revision=0,
            content={"artifact_text": "Исходный черновик", "repository_url": ""}), Response(), auth=(user, None), db=db)
        assert initial.revision == 1

    barrier = Barrier(2)

    def edit(text_value):
        with factory() as db:
            user = db.get(User, sandbox.user_id)
            barrier.wait(timeout=15)
            try:
                result = save_draft(SaveDraft(identity=identity, expected_revision=1,
                    content={"artifact_text": text_value, "repository_url": ""}), Response(), auth=(user, None), db=db)
                return 200, result.content["artifact_text"]
            except HTTPException as error:
                db.rollback()
                return error.status_code, error.detail.get("code")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(edit, ["Первый вариант 🐍", "Второй вариант café"]))
    assert sorted(code for code, _ in results) == [200, 409]
    assert next(value for code, value in results if code == 409) == "draft_conflict"
    winner = next(value for code, value in results if code == 200)
    with factory() as db:
        row = db.scalar(select(StudyDraft).where(StudyDraft.user_id == sandbox.user_id))
        assert row.revision == 2 and row.content["artifact_text"] == winner
        assert db.scalar(select(func.count()).select_from(SkillEvidence).where(SkillEvidence.user_id == sandbox.user_id)) == 0
        # Clearing is a new revision, never a deletion that a stale client can resurrect.
        user = db.get(User, sandbox.user_id)
        tombstone = save_draft(SaveDraft(identity=identity, expected_revision=2, content=None),
                              Response(), auth=(user, None), db=db)
        assert tombstone.revision == 3 and tombstone.content is None
        with pytest.raises(HTTPException) as conflict:
            save_draft(SaveDraft(identity=identity, expected_revision=2,
                content={"artifact_text": "Устаревший вариант", "repository_url": ""}), Response(), auth=(user, None), db=db)
        assert conflict.value.status_code == 409
        db.rollback()
        row = db.scalar(select(StudyDraft).where(StudyDraft.user_id == sandbox.user_id))
        assert row.revision == 3 and row.content is None


def test_postgres_concurrent_starts_share_one_open_study_timer(postgres_engine, sandbox):
    from fastapi import Response
    from app.db.study_session_models import StudySession
    from app.study_sessions import StartRequest, start_session

    _prepare_study_owner(postgres_engine, sandbox.user_id)
    factory = sessionmaker(bind=postgres_engine, autoflush=False, expire_on_commit=False)
    barrier = Barrier(2)

    def start():
        with factory() as db:
            user = db.get(User, sandbox.user_id)
            barrier.wait(timeout=15)
            return start_session(StartRequest(), Response(), auth=(user, None), db=db).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(start) for _ in range(2)]
        ids = [future.result(timeout=30) for future in futures]
    assert ids[0] == ids[1]
    with factory() as db:
        rows = db.scalars(select(StudySession).where(StudySession.user_id == sandbox.user_id)).all()
        assert len(rows) == 1 and rows[0].revision == 1
        assert db.scalar(select(func.count()).select_from(SkillEvidence).where(SkillEvidence.user_id == sandbox.user_id)) == 0


def test_postgres_stale_timer_action_cannot_double_accrue(postgres_engine, sandbox):
    from fastapi import HTTPException, Response
    from app.db.study_session_models import StudySession
    from app.study_sessions import StartRequest, _transition, start_session
    from datetime import timedelta

    _prepare_study_owner(postgres_engine, sandbox.user_id)
    factory = sessionmaker(bind=postgres_engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        current = start_session(StartRequest(), Response(), auth=(db.get(User, sandbox.user_id), None), db=db)
        now = current.started_at + timedelta(seconds=35)
    barrier = Barrier(2)

    def pause():
        with factory() as db:
            barrier.wait(timeout=15)
            try:
                return 200, _transition(db, sandbox.user_id, current.id, "pause", 1, now).active_seconds
            except HTTPException as error:
                db.rollback()
                return error.status_code, None

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(pause) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert sorted(code for code, _ in results) == [200, 409]
    assert next(seconds for code, seconds in results if code == 200) == 35
    with factory() as db:
        row = db.get(StudySession, current.id)
        assert row.status == "paused" and row.revision == 2
        assert row.accumulated_milliseconds == 35000 and row.last_activity_at is None
