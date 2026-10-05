import runpy
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from app.db.models import (
    AssessmentResponse,
    KnowledgeCheckResponse,
    MistakeOccurrence,
    SkillEvidence,
    SkillMasteryAudit,
    User,
    UserMistake,
    UserSkill,
)
from app.db.session import get_db
from app.main import app
from app.mistake_memory import record_response_mistake
from test_auth import client, csrf


def _setup_user(test_client, email):
    assert (
        test_client.post(
            "/auth/register",
            json={"email": email, "password": "safe-password"},
        ).status_code
        == 201
    )
    assert (
        test_client.post(
            "/onboarding",
            headers={"X-CSRF-Token": csrf(test_client)},
            json={
                "experience_level": "beginner",
                "target_role": "Python Backend",
                "weekly_minutes": 180,
            },
        ).status_code
        == 200
    )


def _seed_authored_mappings(db):
    # The API tests use create_all instead of running Alembic; mirror the
    # complete catalog from the migration head, including assessment mappings.
    authored_migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "0024_authored_mistake_mappings.py"
    )
    authored_seed = runpy.run_path(str(authored_migration_path))[
        "seed_authored_mappings"
    ]
    authored_seed(db.connection())
    assessment_migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "0025_assessment_mistake_mappings.py"
    )
    assessment_seed = runpy.run_path(str(assessment_migration_path))[
        "seed_assessment_mappings"
    ]
    assessment_seed(db.connection())
    db.commit()


def _check_answers(questions, *, output, reassignment):
    return {
        "variables-output-v1": output,
        "variables-reassignment-v1": reassignment,
    }


def test_distinct_mapped_mistakes_increment_but_reprocessing_is_idempotent(client):
    _setup_user(client, "mistake-repeat@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    questions = client.get("/learning/lessons/variables-v1/knowledge-check").json()
    with next(app.dependency_overrides[get_db]()) as db:
        _seed_authored_mappings(db)

    first_result = client.post(
        "/learning/lessons/variables-v1/knowledge-check",
        headers=headers,
            json={
                "answers": _check_answers(
                    questions,
                    output="4",
                    reassignment="Увеличивает текущее значение x на 1",
                )
            },
    )
    assert first_result.status_code == 201, first_result.text
    with next(app.dependency_overrides[get_db]()) as db:
        first_response = db.scalar(
            select(KnowledgeCheckResponse).where(
                KnowledgeCheckResponse.question_id == "variables-output-v1",
                KnowledgeCheckResponse.answer == "4",
            )
        )
        aggregate = db.scalar(
            select(UserMistake).where(
                UserMistake.misconception_code == "mis-var-output-first-v1"
            )
        )
        assert aggregate is not None
        assert aggregate.occurrence_count == 1
        assert db.scalar(
            select(func.count()).select_from(MistakeOccurrence).where(
                MistakeOccurrence.misconception_code == "mis-var-output-first-v1"
            )
        ) == 1
        owner_id = aggregate.user_id
        source_id = first_response.id

        mastery_before = db.scalar(
            select(UserSkill).where(
                UserSkill.user_id == owner_id,
                UserSkill.skill_id == "python.variables",
            )
        )
        mastery_snapshot = (
            mastery_before.evidence_count,
            mastery_before.knowledge_score,
            mastery_before.practice_score,
            mastery_before.independent_score,
        )
        evidence_count = db.scalar(
            select(func.count()).select_from(SkillEvidence).where(
                SkillEvidence.user_id == owner_id
            )
        )
        audit_count = db.scalar(
            select(func.count()).select_from(SkillMasteryAudit).where(
                SkillMasteryAudit.user_id == owner_id
            )
        )
        duplicate = record_response_mistake(
            db,
            user_id=owner_id,
            source_type="knowledge_check_response",
            source_id=source_id,
        )
        assert duplicate is not None
        db.flush()
        db.refresh(aggregate)
        db.refresh(mastery_before)
        assert aggregate.occurrence_count == 1
        assert (
            mastery_before.evidence_count,
            mastery_before.knowledge_score,
            mastery_before.practice_score,
            mastery_before.independent_score,
        ) == mastery_snapshot
        assert db.scalar(
            select(func.count()).select_from(SkillEvidence).where(
                SkillEvidence.user_id == owner_id
            )
        ) == evidence_count
        assert db.scalar(
            select(func.count()).select_from(SkillMasteryAudit).where(
                SkillMasteryAudit.user_id == owner_id
            )
        ) == audit_count

    # A correct answer for this question between two wrong responses does not
    # reset the learner's history for this misconception.
    questions = client.get("/learning/lessons/variables-v1/knowledge-check").json()
    middle = client.post(
        "/learning/lessons/variables-v1/knowledge-check",
        headers=headers,
        json={
            "answers": _check_answers(
                questions,
                output="6",
                reassignment="Создаёт вторую переменную x",
            )
        },
    )
    assert middle.status_code == 201
    questions = client.get("/learning/lessons/variables-v1/knowledge-check").json()
    last = client.post(
        "/learning/lessons/variables-v1/knowledge-check",
        headers=headers,
        json={
            "answers": _check_answers(
                questions,
                output="4",
                reassignment="Увеличивает текущее значение x на 1",
            )
        },
    )
    assert last.status_code == 201

    with next(app.dependency_overrides[get_db]()) as db:
        aggregate = db.scalar(
            select(UserMistake).where(
                UserMistake.user_id == owner_id,
                UserMistake.misconception_code == "mis-var-output-first-v1",
            )
        )
        assert aggregate.occurrence_count == 2
        assert db.scalar(
            select(func.count()).select_from(MistakeOccurrence).where(
                MistakeOccurrence.user_id == owner_id,
                MistakeOccurrence.misconception_code == "mis-var-output-first-v1",
            )
        ) == 2
        assert aggregate.first_seen_at <= aggregate.last_seen_at
        assert aggregate.last_source_id != str(source_id)


def test_wrong_owner_cannot_record_another_users_response(client):
    _setup_user(client, "mistake-owner@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    questions = client.get("/learning/lessons/variables-v1/knowledge-check").json()
    with next(app.dependency_overrides[get_db]()) as db:
        _seed_authored_mappings(db)
    response = client.post(
        "/learning/lessons/variables-v1/knowledge-check",
        headers=headers,
        json={
            "answers": _check_answers(
                questions,
                output="4",
                reassignment="Увеличивает текущее значение x на 1",
            )
        },
    )
    assert response.status_code == 201, response.text

    with next(app.dependency_overrides[get_db]()) as db:
        saved_response = db.scalar(
            select(KnowledgeCheckResponse).where(
                KnowledgeCheckResponse.question_id == "variables-output-v1"
            )
        )
        source_id = saved_response.id
        original_user = db.scalar(select(User).where(User.email == "mistake-owner@example.com"))
        original_user_id = original_user.id

    client.post("/auth/logout", headers=headers)
    _setup_user(client, "mistake-other@example.com")
    with next(app.dependency_overrides[get_db]()) as db:
        other_user = db.scalar(select(User).where(User.email == "mistake-other@example.com"))
        result = record_response_mistake(
            db,
            user_id=other_user.id,
            source_type="knowledge_check_response",
            source_id=source_id,
        )
        assert result is None
        assert db.scalar(
            select(UserMistake).where(
                UserMistake.user_id == other_user.id,
                UserMistake.misconception_code == "mis-var-output-first-v1",
            )
        ) is None
        assert db.scalar(
            select(UserMistake).where(
                UserMistake.user_id == original_user_id,
                UserMistake.misconception_code == "mis-var-output-first-v1",
            )
        ).occurrence_count == 1


def test_new_mistake_write_does_not_change_mastery_or_evidence(client, monkeypatch):
    _setup_user(client, "mistake-mastery-boundary@example.com")
    questions = client.get("/learning/lessons/variables-v1/knowledge-check").json()
    with next(app.dependency_overrides[get_db]()) as db:
        _seed_authored_mappings(db)

    # Persist/grading still uses its existing evidence path; suppress only the
    # automatic mistake call so this test exercises a genuinely new memory
    # write against an already-established mastery snapshot.
    monkeypatch.setattr("app.knowledge_check.record_response_mistake", lambda *args, **kwargs: None)
    response = client.post(
        "/learning/lessons/variables-v1/knowledge-check",
        headers={"X-CSRF-Token": csrf(client)},
        json={
            "answers": _check_answers(
                questions,
                output="4",
                reassignment="Увеличивает текущее значение x на 1",
            )
        },
    )
    assert response.status_code == 201

    with next(app.dependency_overrides[get_db]()) as db:
        saved_response = db.scalar(
            select(KnowledgeCheckResponse).where(
                KnowledgeCheckResponse.question_id == "variables-output-v1"
            )
        )
        user = db.scalar(select(User).where(User.email == "mistake-mastery-boundary@example.com"))
        user_skill = db.scalar(
            select(UserSkill).where(
                UserSkill.user_id == user.id,
                UserSkill.skill_id == "python.variables",
            )
        )
        mastery_fields = (
            "knowledge_score",
            "practice_score",
            "independent_score",
            "retention_score",
            "confidence",
            "mastery_weight",
            "evidence_count",
            "last_practiced_at",
            "next_review_at",
        )
        before = tuple(getattr(user_skill, field) for field in mastery_fields)
        evidence_before = db.scalar(
            select(func.count()).select_from(SkillEvidence).where(
                SkillEvidence.user_id == user.id
            )
        )
        audits_before = db.scalar(
            select(func.count()).select_from(SkillMasteryAudit).where(
                SkillMasteryAudit.user_id == user.id
            )
        )
        recorded = record_response_mistake(
            db,
            user_id=user.id,
            source_type="knowledge_check_response",
            source_id=saved_response.id,
        )
        assert recorded is not None
        db.flush()
        db.refresh(user_skill)
        assert tuple(getattr(user_skill, field) for field in mastery_fields) == before
        assert db.scalar(
            select(func.count()).select_from(SkillEvidence).where(
                SkillEvidence.user_id == user.id
            )
        ) == evidence_before
        assert db.scalar(
            select(func.count()).select_from(SkillMasteryAudit).where(
                SkillMasteryAudit.user_id == user.id
            )
        ) == audits_before


def test_assessment_wrong_response_uses_only_its_exact_authored_mapping(
    client, monkeypatch
):
    _setup_user(client, "mistake-assessment@example.com")
    first_question = client.get("/assessment").json()["question"]
    assert first_question["id"] == "variables-v1"
    with next(app.dependency_overrides[get_db]()) as db:
        _seed_authored_mappings(db)

    observed_calls = []
    actual_service = record_response_mistake

    def observe_persisted_response(db, **kwargs):
        response_id = UUID(str(kwargs["source_id"]))
        persisted = db.get(AssessmentResponse, response_id)
        assert persisted is not None
        assert persisted.is_correct is False
        observed_calls.append((kwargs["source_type"], response_id))
        return actual_service(db, **kwargs)

    monkeypatch.setattr(
        "app.assessment.record_response_mistake",
        observe_persisted_response,
    )
    submitted = client.post(
        "/assessment/answers",
        headers={"X-CSRF-Token": csrf(client)},
        json={"question_id": first_question["id"], "answer": "4"},
    )
    assert submitted.status_code == 200
    assert len(observed_calls) == 1
    assert observed_calls[0][0] == "assessment_response"

    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(
            select(AssessmentResponse).where(
                AssessmentResponse.id == observed_calls[0][1]
            )
        ) is not None
        occurrence = db.scalar(
            select(MistakeOccurrence).where(
                MistakeOccurrence.source_type == "assessment_response",
                MistakeOccurrence.source_id == str(observed_calls[0][1]),
            )
        )
        assert occurrence is not None
        aggregate = db.scalar(
            select(UserMistake).where(
                UserMistake.user_id == occurrence.user_id,
                UserMistake.misconception_code == "mis-var-output-first-v1",
            )
        )
        assert aggregate is not None
        assert aggregate.occurrence_count == 1
