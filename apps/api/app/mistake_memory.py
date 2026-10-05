"""Write only author-classified response mismatches to learner mistake memory."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import case, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.models import (
    AssessmentResponse,
    AssessmentRun,
    ExerciseVersion,
    KnowledgeCheckAttempt,
    KnowledgeCheckResponse,
    Misconception,
    MisconceptionMapping,
    MisconceptionVersion,
    MistakeOccurrence,
    User,
    UserMistake,
)
from app.exercise_snapshots import snapshot_assessment, snapshot_checks


_SOURCE_TYPES = {
    "knowledge_check_response",
    "assessment_response",
}


def _owned_response(db: Session, user_id: UUID, source_type: str, source_id: UUID):
    """Return a response only through its owning attempt/run for this learner."""

    if source_type == "knowledge_check_response":
        row = db.execute(
            select(KnowledgeCheckResponse, KnowledgeCheckAttempt)
            .join(
                KnowledgeCheckAttempt,
                KnowledgeCheckAttempt.id == KnowledgeCheckResponse.attempt_id,
            )
            .where(
                KnowledgeCheckResponse.id == source_id,
                KnowledgeCheckAttempt.user_id == user_id,
            )
        ).first()
        if row is None:
            return None
        response, attempt = row
        if response.is_correct or attempt.exercise_version_id is None:
            return None
        version = db.get(ExerciseVersion, attempt.exercise_version_id)
        if version is None:
            return None
        snapshot = version.content_snapshot
        if not isinstance(snapshot, dict):
            return None
        lesson = snapshot.get("lesson")
        questions = snapshot_checks(snapshot)
        matches = [q for q in questions if isinstance(q, dict) and q.get("id") == response.question_id]
        if (
            len(matches) != 1
            or version.exercise_id != attempt.lesson_id
            or version.version < 1
            or snapshot.get("exercise_id") != version.exercise_id
            or snapshot.get("version") != version.version
            or not isinstance(lesson, dict)
            or lesson.get("id") != attempt.lesson_id
            or lesson.get("skill_id") != attempt.skill_id
        ):
            return None
        question = matches[0]
        if (
            not isinstance(question.get("choices"), list)
            or response.answer not in question["choices"]
            or not isinstance(question.get("answer"), str)
            or question["answer"] not in question["choices"]
            or response.answer == question["answer"]
            or response.explanation != question.get("explanation")
        ):
            return None
        return response, version, attempt.lesson_id, attempt.skill_id

    if source_type == "assessment_response":
        row = db.execute(
            select(AssessmentResponse, AssessmentRun)
            .join(AssessmentRun, AssessmentRun.id == AssessmentResponse.run_id)
            .where(
                AssessmentResponse.id == source_id,
                AssessmentRun.user_id == user_id,
            )
        ).first()
        if row is None:
            return None
        response, run = row
        if response.is_correct or response.exercise_version_id is None:
            return None
        version = db.get(ExerciseVersion, response.exercise_version_id)
        if version is None or version.exercise_id != response.question_id:
            return None
        snapshot = version.content_snapshot
        if not isinstance(snapshot, dict):
            return None
        question = snapshot_assessment(snapshot)
        if (
            question is None
            or version.version < 1
            or snapshot.get("exercise_id") != version.exercise_id
            or snapshot.get("version") != version.version
            or question.get("id") != response.question_id
            or question.get("skill_id") != response.skill_id
            or question.get("difficulty") != response.difficulty
            or not isinstance(question.get("choices"), list)
            or response.answer not in question["choices"]
            or not isinstance(question.get("answer"), str)
            or question["answer"] not in question["choices"]
            or response.answer == question["answer"]
        ):
            return None
        return response, version, version.lesson_id, response.skill_id

    return None


def record_response_mistake(
    db: Session,
    *,
    user_id: UUID,
    source_type: str,
    source_id: str | UUID,
) -> MistakeOccurrence | None:
    """Record one persisted, owned, precisely mapped wrong response.

    Unknown or correct responses intentionally produce no memory record. This
    service does not write evidence, mastery projections, or mastery audits.
    The caller owns the surrounding transaction.
    """

    if source_type not in _SOURCE_TYPES:
        return None
    try:
        parsed_source_id = UUID(str(source_id))
    except (TypeError, ValueError, AttributeError):
        return None

    # Serialize this learner's memory writes on PostgreSQL. SQLite ignores
    # FOR UPDATE, but still provides the same transactional behavior in tests.
    if db.scalar(select(User.id).where(User.id == user_id).with_for_update()) is None:
        return None

    source = _owned_response(db, user_id, source_type, parsed_source_id)
    if source is None:
        return None
    response, exercise_version, lesson_id, skill_id = source

    mapped = db.execute(
        select(MisconceptionMapping, Misconception)
        .join(Misconception, Misconception.code == MisconceptionMapping.misconception_code)
        .where(
            MisconceptionMapping.source_type == source_type,
            MisconceptionMapping.exercise_id == exercise_version.exercise_id,
            MisconceptionMapping.exercise_version == exercise_version.version,
            MisconceptionMapping.question_id == response.question_id,
            MisconceptionMapping.wrong_choice == response.answer,
        )
    ).first()
    if mapped is None:
        # A wrong choice without an exact author-approved mapping is not a
        # diagnosis and must not fall back to a generic topic-level record.
        return None
    mapping, misconception = mapped
    if misconception.skill_id != skill_id:
        return None
    catalog_version = db.get(MisconceptionVersion, mapping.misconception_version_id)
    if (
        catalog_version is None
        or catalog_version.misconception_code != mapping.misconception_code
    ):
        return None

    aggregate = db.scalar(
        select(UserMistake)
        .where(
            UserMistake.user_id == user_id,
            UserMistake.misconception_code == mapping.misconception_code,
        )
        .with_for_update()
    )
    aggregate_created = aggregate is None
    occurred_at = response.created_at
    if aggregate_created:
        aggregate = UserMistake(
            user_id=user_id,
            misconception_code=mapping.misconception_code,
            skill_id=misconception.skill_id,
            lesson_id=lesson_id,
            occurrence_count=1,
            first_seen_at=occurred_at,
            last_seen_at=occurred_at,
            last_source_type=source_type,
            last_source_id=str(parsed_source_id),
        )
        db.add(aggregate)
        db.flush()

    values = {
        "id": uuid4(),
        "user_id": user_id,
        "user_mistake_id": aggregate.id,
        "misconception_code": mapping.misconception_code,
        "misconception_version_id": mapping.misconception_version_id,
        "source_type": source_type,
        "source_id": str(parsed_source_id),
        "lesson_id": lesson_id,
        "occurred_at": occurred_at,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        insert = postgresql_insert
    elif dialect == "sqlite":
        insert = sqlite_insert
    else:  # pragma: no cover - the application supports PostgreSQL and SQLite
        raise RuntimeError(f"Unsupported database dialect for mistake memory: {dialect}")
    occurrence_id = db.execute(
        insert(MistakeOccurrence)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[
                MistakeOccurrence.source_type,
                MistakeOccurrence.source_id,
                MistakeOccurrence.misconception_code,
            ]
        )
        .returning(MistakeOccurrence.id)
    ).scalar_one_or_none()
    if occurrence_id is None:
        if aggregate_created:
            raise RuntimeError("Mistake aggregate exists without its source occurrence")
        return db.scalar(
            select(MistakeOccurrence).where(
                MistakeOccurrence.user_id == user_id,
                MistakeOccurrence.source_type == source_type,
                MistakeOccurrence.source_id == str(parsed_source_id),
                MistakeOccurrence.misconception_code == mapping.misconception_code,
            )
        )

    if not aggregate_created:
        is_latest = occurred_at >= UserMistake.last_seen_at
        db.execute(
            update(UserMistake)
            .where(UserMistake.id == aggregate.id, UserMistake.user_id == user_id)
            .values(
                occurrence_count=UserMistake.occurrence_count + 1,
                first_seen_at=case(
                    (occurred_at < UserMistake.first_seen_at, occurred_at),
                    else_=UserMistake.first_seen_at,
                ),
                last_seen_at=case(
                    (is_latest, occurred_at),
                    else_=UserMistake.last_seen_at,
                ),
                lesson_id=case((is_latest, lesson_id), else_=UserMistake.lesson_id),
                last_source_type=case(
                    (is_latest, source_type),
                    else_=UserMistake.last_source_type,
                ),
                last_source_id=case(
                    (is_latest, str(parsed_source_id)),
                    else_=UserMistake.last_source_id,
                ),
                updated_at=datetime.now(timezone.utc),
            )
        )
    return db.get(MistakeOccurrence, occurrence_id)
