import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import LessonCompletion, LessonSkill, Skill, SkillEdge, SkillEvidence, User, UserSkill
from app.db.session import get_db
from app.main import app
from app.skill_graph import EDGES, LESSON_SKILLS, SKILLS, seed_skill_graph, validate_graph
from test_auth import client, csrf


def test_authored_graph_has_valid_references_and_acyclic_prerequisites():
    validate_graph()
    ids = {skill["id"] for skill in SKILLS}
    assert 80 <= len(ids) <= 150
    assert all(source in ids and target in ids for source, target, _ in EDGES)
    assert all(skill in ids for _, skill in LESSON_SKILLS)
    assert ("variables-v1", "python.data_types") not in LESSON_SKILLS
    assert ("variables-v1", "python.variables") in LESSON_SKILLS

    original = EDGES[:]
    try:
        EDGES.append([SKILLS[1]["id"], SKILLS[0]["id"], "prerequisite"])
        with pytest.raises(ValueError, match="Cycle"):
            validate_graph()
    finally:
        EDGES[:] = original


def test_seed_is_idempotent_and_stores_lesson_links(client):
    assert client.post("/auth/register", json={"email": "skills@example.com", "password": "safe-password"}).status_code == 201
    assert client.post("/onboarding", headers={"X-CSRF-Token": csrf(client)}, json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180,
    }).status_code == 200
    first = client.get("/skills/graph")
    second = client.get("/skills/graph")
    assert first.status_code == second.status_code == 200
    assert len(first.json()["skills"]) == len(SKILLS)
    assert first.json() == second.json()
    assert first.json()["skills"][0]["importance"] > 0
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(Skill).where(Skill.id == "python.variables")) is not None
        assert len(db.scalars(select(SkillEdge)).all()) == len({tuple(edge) for edge in EDGES})
        assert len(db.scalars(select(LessonSkill)).all()) == len(LESSON_SKILLS)


def test_learning_path_uses_prerequisite_evidence(client):
    assert client.post("/auth/register", json={"email": "prereq@example.com", "password": "safe-password"}).status_code == 201
    assert client.post("/onboarding", headers={"X-CSRF-Token": csrf(client)}, json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180,
    }).status_code == 200
    assert client.get("/learning/lessons/conditions-v1").status_code == 409
    response = client.post("/learning/lessons/variables-v1/complete",
                           headers={"X-CSRF-Token": csrf(client)}, json={"answer": "6"})
    assert response.status_code == 200
    assert response.json()["path"]["next_lesson_id"] == "data-types-v1"
    assert client.get("/learning/lessons/conditions-v1").status_code == 409


def test_legacy_secondary_lesson_skill_link_does_not_bypass_types_prerequisite(client):
    assert client.post("/auth/register", json={"email": "legacy-secondary@example.com", "password": "safe-password"}).status_code == 201
    assert client.post("/onboarding", headers={"X-CSRF-Token": csrf(client)}, json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180,
    }).status_code == 200
    assert client.post(
        "/learning/lessons/variables-v1/complete",
        headers={"X-CSRF-Token": csrf(client)},
        json={"answer": "6"},
    ).status_code == 200
    with next(app.dependency_overrides[get_db]()) as db:
        db.add(LessonSkill(
            lesson_id="variables-v1",
            skill_id="python.data_types",
        ))
        db.commit()
    path = client.get("/learning/path")
    assert path.status_code == 200
    assert path.json()["next_lesson_id"] == "data-types-v1"
    assert client.get("/learning/lessons/conditions-v1").status_code == 409


def test_mastery_fallback_is_consistent_across_path_plan_and_curriculum(client):
    assert client.post("/auth/register", json={"email": "mastery-fallback@example.com", "password": "safe-password"}).status_code == 201
    assert client.post("/onboarding", headers={"X-CSRF-Token": csrf(client)}, json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180,
    }).status_code == 200
    with next(app.dependency_overrides[get_db]()) as db:
        from app.db.models import User, UserSkill

        user = db.scalar(select(User))
        db.add(UserSkill(
            user_id=user.id,
            skill_id="python.variables",
            evidence_count=1,
            independent_score=1.0,
            knowledge_score=1.0,
            practice_score=1.0,
        ))
        db.add(UserSkill(
            user_id=user.id,
            skill_id="python.data_types",
            evidence_count=1,
            independent_score=1.0,
            knowledge_score=1.0,
            practice_score=1.0,
        ))
        db.add(LessonCompletion(
            user_id=user.id,
            lesson_id="variables-v1",
            answer="6",
        ))
        user_id = user.id
        db.commit()

    path = client.get("/learning/path")
    assert path.status_code == 200
    assert path.json()["next_lesson_id"] == "data-types-v1"
    assert client.get("/learning/lessons/data-types-v1").status_code == 200

    from app.learning_plan import generate_plan
    from app.curriculum import build_curriculum
    from app.db.models import AssessmentRun

    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        run = AssessmentRun(user_id=user.id, status="completed")
        db.add(run)
        db.flush()
        generate_plan(db, user, run)
        build_curriculum(db, user)
        db.commit()
    plan = client.get("/learning/plan").json()
    assert plan["recommended_lesson_id"] == "data-types-v1"
    assert next(item for item in plan["items"] if item["lesson_id"] == "data-types-v1")["status"] == "recommended"
    curriculum = client.get("/learning/curriculum").json()
    activities = [
        activity
        for session in curriculum["sessions"]
        for activity in session["activities"]
    ]
    assert any(activity["lesson_id"] == "data-types-v1" for activity in activities)

    # A previously built curriculum revision remains immutable, while the live
    # response must not present its now-locked item as available.
    with next(app.dependency_overrides[get_db]()) as db:
        db.query(UserSkill).filter(UserSkill.user_id == user_id).delete()
        db.commit()
    locked_path = client.get("/learning/path").json()
    assert locked_path["next_lesson_id"] == "data-types-v1"
    locked_plan = client.get("/learning/plan").json()
    assert locked_plan["recommended_lesson_id"] == "data-types-v1"
    assert next(
        item for item in locked_plan["items"]
        if item["lesson_id"] == "data-types-v1"
    )["status"] == "recommended"
    locked_curriculum = client.get("/learning/curriculum").json()
    old_condition = next(
        activity
        for session in locked_curriculum["sessions"]
        for activity in session["activities"]
        if activity["lesson_id"] == "conditions-v1"
    )
    assert old_condition["availability"] == "locked"


def test_skill_evidence_assistance_constraints_reject_invalid_pairs(client):
    assert client.post("/auth/register", json={"email": "evidence-db@example.com", "password": "safe-password"}).status_code == 201
    onboard = client.post(
        "/onboarding",
        headers={"X-CSRF-Token": csrf(client)},
        json={"experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180},
    )
    assert onboard.status_code == 200
    assert client.get("/learning/path").status_code == 200

    invalid_values = ((False, 1), (True, 0), (False, 6), (True, 6))
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        for assisted, hint_count in invalid_values:
            db.add(
                SkillEvidence(
                    user_id=user.id,
                    skill_id="python.variables",
                    source_type="assessment_response",
                    source_id=str(uuid4()),
                    result_score=1.0,
                    assisted=assisted,
                    hint_count=hint_count,
                    occurred_at=datetime.now(timezone.utc),
                    idempotency_key=str(uuid4()),
                )
            )
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
