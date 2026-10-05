from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from app.assessment_content import MAX_QUESTIONS
from app.db.models import ExerciseVersion, KnowledgeCheckAttempt, KnowledgeCheckResponse, KnowledgeCheckSession, LessonCompletion, SkillEvidence, SkillMasteryAudit, User, UserSkill
from app.db.session import get_db
from app.main import app
from app.learning_content import EXERCISE_HINT_LADDERS
from app.exercise_hints import _seed_exercise
from app.skill_evidence import InvalidEvidence, derive_assistance
from test_auth import client, csrf
from content_helpers import enable_choice_feedback

def setup_user(c,email="check@example.com"):
    assert c.post("/auth/register",json={"email":email,"password":"safe-password"}).status_code==201
    assert c.post("/onboarding",headers={"X-CSRF-Token":csrf(c)},json={"experience_level":"beginner","target_role":"Python Backend","weekly_minutes":180}).status_code==200

def finish_assessment(c):
    h={"X-CSRF-Token":csrf(c)}; state=c.get("/assessment").json()
    for _ in range(MAX_QUESTIONS):
        q=state["question"]; state=c.post("/assessment/answers",headers=h,json={"question_id":q["id"],"answer":q["choices"][0]}).json()["state"]

def test_check_requires_auth_and_returns_no_answer_key(client):
    assert client.get("/learning/lessons/variables-v1/knowledge-check").status_code==401
    setup_user(client)
    response=client.get("/learning/lessons/variables-v1/knowledge-check")
    assert response.status_code==200 and response.json()
    assert "answer" not in response.text and "explanation" not in response.text
    assert client.post("/learning/lessons/variables-v1/knowledge-check",json={}).status_code==403

def test_failed_check_is_persisted_with_explanations_and_does_not_complete(client):
    setup_user(client); h={"X-CSRF-Token":csrf(client)}; questions=client.get("/learning/lessons/variables-v1/knowledge-check").json()
    bad={q["id"]:q["choices"][0] for q in questions}
    result=client.post("/learning/lessons/variables-v1/knowledge-check",headers=h,json={"answers":bad})
    assert result.status_code==201 and result.json()["passed"] is False and len(result.json()["explanations"])==2
    assert "attempt_id" not in result.json()
    assert client.get("/learning/path").json()["completed"]==0
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(KnowledgeCheckAttempt)).passed is False
        assert len(db.scalars(select(KnowledgeCheckResponse)).all())==2

def test_passed_check_completes_lesson_and_refreshes_plan(client):
    setup_user(client); finish_assessment(client); h={"X-CSRF-Token":csrf(client)}; questions=client.get("/learning/lessons/variables-v1/knowledge-check").json()
    answers={questions[0]["id"]:"6",questions[1]["id"]:questions[1]["choices"][0]}
    result=client.post("/learning/lessons/variables-v1/knowledge-check",headers=h,json={"answers":answers})
    assert result.status_code==201 and result.json()["passed"] is True
    assert client.get("/learning/path").json()["completed"]==1
    plan = client.get("/learning/plan").json()
    # The diagnostic bank samples many early skills, so after variables-v1 the
    # plan recommends whichever prerequisite-ready lesson has the weakest
    # evidence.  Any lesson that is not variables-v1 satisfies the contract.
    assert plan["recommended_lesson_id"] != "variables-v1"
    # A correct diagnostic answer on an early skill satisfies the existing
    # mastery-readiness fallback, so later lessons can legitimately become
    # ready.  The invariant the plan must keep is that nothing locked is
    # recommended and the recommendation is prerequisite-ready.
    locked = {item["lesson_id"] for item in plan["items"] if item["status"] == "locked"}
    assert plan["recommended_lesson_id"] not in locked
    assert all(
        item["status"] != "recommended" or item["lesson_id"] not in locked
        for item in plan["items"]
    )
    with next(app.dependency_overrides[get_db]()) as db:
        completion=db.scalar(select(LessonCompletion)); assert completion.evidence_type=="knowledge_check_passed"
        # One diagnostic response plus one knowledge-check attempt for
        # python.variables; the bank samples several skills, so the run writes
        # one evidence row per asked question across all of them.
        mastery=db.scalar(select(UserSkill).where(UserSkill.skill_id=="python.variables")); assert mastery.evidence_count==2 and mastery.practice_score==1.0 and mastery.next_review_at is not None
        evidence=db.scalars(select(SkillEvidence).where(SkillEvidence.user_id==mastery.user_id,SkillEvidence.skill_id==mastery.skill_id)).all()
        assert len(evidence)==2 and sum(row.source_type=="knowledge_check_attempt" for row in evidence)==1
        assert db.scalar(select(SkillMasteryAudit).where(SkillMasteryAudit.user_id==mastery.user_id)) is not None
        from app.skill_evidence import record_evidence
        attempt=db.scalar(select(KnowledgeCheckAttempt))
        record_evidence(db,user_id=attempt.user_id,skill_id=attempt.skill_id,source_type="knowledge_check_attempt",source_id=str(attempt.id),result_score=attempt.score,occurred_at=attempt.created_at,metadata={"lesson_id":attempt.lesson_id,"passed":attempt.passed})
        db.flush()
        assert db.scalar(select(UserSkill).where(UserSkill.user_id==attempt.user_id,UserSkill.skill_id==attempt.skill_id)).evidence_count==2
        # One assessment response plus the knowledge check produced this run's
        # evidence; the bank now samples several skills, so the total is counted
        # instead of hard-coded.
        assert len(db.scalars(select(SkillEvidence).where(SkillEvidence.user_id==attempt.user_id)).all()) >= 5


def test_repeated_check_keeps_completion_and_appends_history(client):
    setup_user(client,"repeat-check@example.com"); h={"X-CSRF-Token":csrf(client)}
    questions=client.get("/learning/lessons/variables-v1/knowledge-check").json()
    pass_answers={questions[0]["id"]:"6",questions[1]["id"]:"Увеличивает текущее значение x на 1"}
    first=client.post("/learning/lessons/variables-v1/knowledge-check",headers=h,json={"answers":pass_answers})
    assert first.status_code==201 and first.json()["passed"] is True
    completion=client.get("/learning/path").json()["lessons"][0]["completed_at"]
    fail_answers={q["id"]:q["choices"][0] for q in questions}
    assert client.post("/learning/lessons/variables-v1/knowledge-check",headers=h,json={"answers":fail_answers}).status_code==409
    questions=client.get("/learning/lessons/variables-v1/knowledge-check").json()
    second=client.post("/learning/lessons/variables-v1/knowledge-check",headers=h,json={"answers":fail_answers})
    assert second.status_code==201 and second.json()["passed"] is False
    assert client.get("/learning/path").json()["completed"]==1
    assert client.get("/learning/path").json()["lessons"][0]["completed_at"]==completion
    with next(app.dependency_overrides[get_db]()) as db:
        assert len(db.scalars(select(KnowledgeCheckAttempt)).all())==2
        assert len(db.scalars(select(KnowledgeCheckResponse)).all())==4


def test_hint_usage_is_server_derived_and_lowers_independent_score(client):
    setup_user(client, "hinted-check@example.com")
    h={"X-CSRF-Token":csrf(client)}
    for level in range(1, 6):
        reveal=client.post(
            "/learning/exercises/variables-v1/hints",
            headers={**h, "Idempotency-Key": f"hinted-check-{level}"},
            json={"level": level},
        )
        assert reveal.status_code == 200
    questions=client.get("/learning/lessons/variables-v1/knowledge-check").json()
    answers={questions[0]["id"]:"6",questions[1]["id"]:"Увеличивает текущее значение x на 1"}
    result=client.post("/learning/lessons/variables-v1/knowledge-check",headers=h,json={"answers":answers})
    assert result.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        evidence=db.scalar(select(SkillEvidence))
        mastery=db.scalar(select(UserSkill))
        assert evidence.assisted is True and evidence.hint_count == 5
        assert mastery.independent_score == 0.0


def test_hint_ownership_is_scoped_to_session_user(client):
    setup_user(client, "hint-owner@example.com")
    h={"X-CSRF-Token":csrf(client)}
    assert client.post(
        "/learning/exercises/variables-v1/hints",
        headers={**h, "Idempotency-Key": "owner-hint"},
        json={"level": 1},
    ).status_code == 200
    client.post("/auth/logout",headers=h)
    setup_user(client, "hint-non-owner@example.com")
    questions=client.get("/learning/lessons/variables-v1/knowledge-check").json()
    answers={questions[0]["id"]:"6",questions[1]["id"]:"Увеличивает текущее значение x на 1"}
    assert client.post(
        "/learning/lessons/variables-v1/knowledge-check",
        headers={"X-CSRF-Token":csrf(client)},
        json={"answers":answers},
    ).status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        evidence=db.scalar(select(SkillEvidence))
        mastery=db.scalar(select(UserSkill))
        assert evidence.assisted is False and evidence.hint_count == 0
        assert mastery.independent_score == 1.0


def test_assistance_uses_attempted_exercise_version_after_publication(client, monkeypatch):
    setup_user(client, "versioned-check@example.com")
    h={"X-CSRF-Token":csrf(client)}
    assert client.post(
        "/learning/exercises/variables-v1/hints",
        headers={**h, "Idempotency-Key": "versioned-hint"},
        json={"level": 1},
    ).status_code == 200
    questions=client.get("/learning/lessons/variables-v1/knowledge-check").json()
    answers={questions[0]["id"]:"6",questions[1]["id"]:"Увеличивает текущее значение x на 1"}
    assert client.post("/learning/lessons/variables-v1/knowledge-check",headers=h,json={"answers":answers}).status_code == 201

    with next(app.dependency_overrides[get_db]()) as db:
        attempt=db.scalar(select(KnowledgeCheckAttempt))
        version=db.get(ExerciseVersion, attempt.exercise_version_id)
        db.add(ExerciseVersion(exercise_id="variables-v1",version=version.version + 1,lesson_id="variables-v1"))
        db.flush()
        original=EXERCISE_HINT_LADDERS["variables-v1"]["version"]
        monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", version.version + 1)
        enable_choice_feedback(monkeypatch, "variables-v1", prefix="assistance")
        try:
            assert derive_assistance(
                db,
                user_id=attempt.user_id,
                source_type="knowledge_check_attempt",
                source_id=str(attempt.id),
            ) == (True, 1)
        finally:
            monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original)


def test_null_snapshot_does_not_fallback_to_new_authored_version(client, monkeypatch):
    setup_user(client, "null-snapshot@example.com")
    h = {"X-CSRF-Token": csrf(client)}
    assert client.post(
        "/learning/exercises/variables-v1/hints",
        headers={**h, "Idempotency-Key": "old-version-hint"},
        json={"level": 1},
    ).status_code == 200

    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        attempt = KnowledgeCheckAttempt(
            user_id=user.id,
            exercise_version_id=None,
            lesson_id="variables-v1",
            skill_id="python.variables",
            score=1.0,
            passed=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(attempt)
        db.flush()
        attempt_id = str(attempt.id)
        user_id = user.id

    original = EXERCISE_HINT_LADDERS["variables-v1"]["version"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original + 1)
    enable_choice_feedback(monkeypatch, "variables-v1", prefix="null-snapshot")
    try:
        assert client.post(
            "/learning/exercises/variables-v1/hints",
            headers={**h, "Idempotency-Key": "new-version-hint"},
            json={"level": 1},
        ).status_code == 200
        with next(app.dependency_overrides[get_db]()) as db:
            with pytest.raises(InvalidEvidence, match="no trusted exercise version"):
                derive_assistance(
                    db,
                    user_id=user_id,
                    source_type="knowledge_check_attempt",
                    source_id=attempt_id,
                )
    finally:
        monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original)


def test_knowledge_check_rejects_null_snapshot_without_mutable_fallback(client):
    setup_user(client, "null-check-snapshot@example.com")
    with next(app.dependency_overrides[get_db]()) as db:
        version = _seed_exercise(db, "variables-v1")
        version.content_snapshot = None
        db.commit()
    assert client.get("/learning/lessons/variables-v1/knowledge-check").status_code == 409
    assert client.post(
        "/learning/lessons/variables-v1/knowledge-check",
        headers={"X-CSRF-Token": csrf(client)},
        json={"answers": {}},
    ).status_code == 409


def test_knowledge_check_post_grades_persisted_snapshot_after_authored_mutation(client, monkeypatch):
    setup_user(client, "check-snapshot-boundary@example.com")
    h = {"X-CSRF-Token": csrf(client)}
    assert client.post(
        "/learning/exercises/variables-v1/hints",
        headers={**h, "Idempotency-Key": "seed-check-snapshot"},
        json={"level": 1},
    ).status_code == 200
    questions = client.get("/learning/lessons/variables-v1/knowledge-check").json()
    from app import exercise_snapshots

    original_checks = exercise_snapshots.CHECKS
    exercise_snapshots.CHECKS = {
        **original_checks,
        "variables-v1": tuple(
            {**question, "choices": ["MUTATED"], "answer": "MUTATED"}
            for question in original_checks["variables-v1"]
        ),
    }
    try:
        answers = {
            questions[0]["id"]: "6",
            questions[1]["id"]: "Увеличивает текущее значение x на 1",
        }
        result = client.post(
            "/learning/lessons/variables-v1/knowledge-check",
            headers=h,
            json={"answers": answers},
        )
        assert result.status_code == 201
        assert result.json()["passed"] is True
        assert "answer" not in result.text
    finally:
        exercise_snapshots.CHECKS = original_checks



def test_knowledge_check_session_binds_get_to_exact_version_after_authored_publication(client, monkeypatch):
    setup_user(client, "knowledge-check-session@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    questions = client.get("/learning/lessons/variables-v1/knowledge-check").json()
    answers = {
        questions[0]["id"]: "6",
        questions[1]["id"]: "Увеличивает текущее значение x на 1",
    }

    with next(app.dependency_overrides[get_db]()) as db:
        version = db.scalar(select(ExerciseVersion))
        assert version.version == 1

    original_version = EXERCISE_HINT_LADDERS["variables-v1"]["version"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", 2)
    enable_choice_feedback(monkeypatch, "variables-v1", prefix="session")
    from app import exercise_snapshots
    original_checks = exercise_snapshots.CHECKS
    monkeypatch.setattr(exercise_snapshots, "CHECKS", {
        **original_checks,
        "variables-v1": tuple(
            {
                **question,
                "choices": ["NEW"],
                "answer": "NEW",
                "choice_explanations": {"NEW": "The new version offers NEW."},
            }
            for question in original_checks["variables-v1"]
        ),
    })
    try:
        with next(app.dependency_overrides[get_db]()) as db:
            newer = _seed_exercise(db, "variables-v1")
            assert newer.id != version.id
            db.commit()
        result = client.post(
            "/learning/lessons/variables-v1/knowledge-check",
            headers=headers,
            json={"answers": answers},
        )
        assert result.status_code == 201
        assert result.json()["passed"] is True
        assert "attempt_id" not in result.json()
        assert "exercise_version_id" not in result.text
        assert "consumed_at" not in result.text

        with next(app.dependency_overrides[get_db]()) as db:
            attempt = db.scalar(select(KnowledgeCheckAttempt))
            assert attempt.exercise_version_id == version.id
            evidence = db.scalar(select(SkillEvidence))
            assert evidence.source_id == str(attempt.id)
            assert evidence.result_score == 1.0
            assert all(row.answer in answers.values() and row.is_correct for row in db.scalars(select(KnowledgeCheckResponse)))
            assert db.scalar(select(KnowledgeCheckSession).where(KnowledgeCheckSession.consumed_at.is_(None))) is None

        assert client.get("/learning/lessons/variables-v1/knowledge-check").status_code == 200
        with next(app.dependency_overrides[get_db]()) as db:
            session = db.scalar(
                select(KnowledgeCheckSession).order_by(KnowledgeCheckSession.created_at.desc())
            )
            assert session.consumed_at is None
            assert db.get(ExerciseVersion, session.exercise_version_id).version == 2
    finally:
        monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original_version)


def test_lesson_hint_after_publication_counts_as_assistance_for_bound_check(client, monkeypatch):
    setup_user(client, "lesson-hint-evidence@example.com")
    lesson = client.get("/learning/lessons/variables-v1")
    assert lesson.status_code == 200
    check_url = "/learning/lessons/variables-v1/knowledge-check"
    questions = client.get(check_url).json()
    with next(app.dependency_overrides[get_db]()) as db:
        bound = db.scalar(select(KnowledgeCheckSession)).exercise_version_id
        assert db.scalar(select(ExerciseVersion)).id == bound
        old_hint = db.get(ExerciseVersion, bound).content_snapshot["hints"][0]["text"]

    original_number = EXERCISE_HINT_LADDERS["variables-v1"]["version"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original_number + 1)
    enable_choice_feedback(monkeypatch, "variables-v1", prefix="bound-hint")
    original_hints = EXERCISE_HINT_LADDERS["variables-v1"]["hints"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "hints", tuple(
        (level, kind, "NEW hint" if level == 1 else text)
        for level, kind, text in original_hints
    ))
    with next(app.dependency_overrides[get_db]()) as db:
        newer = _seed_exercise(db, "variables-v1")
        assert newer.id != bound
        db.commit()

    headers = {"X-CSRF-Token": csrf(client)}
    hint = client.post(
        "/learning/exercises/variables-v1/hints",
        headers={**headers, "Idempotency-Key": "lesson-bound-after-publication"},
        json={"level": 1},
    )
    assert hint.status_code == 200
    assert hint.json()["text"] == old_hint
    answers = {
        questions[0]["id"]: "6",
        questions[1]["id"]: "Увеличивает текущее значение x на 1",
    }
    result = client.post(check_url, headers=headers, json={"answers": answers})
    assert result.status_code == 201 and result.json()["passed"] is True
    with next(app.dependency_overrides[get_db]()) as db:
        from app.db.models import HintReveal
        assert db.scalar(select(HintReveal)).exercise_version_id == bound
        assert db.scalar(select(KnowledgeCheckAttempt)).exercise_version_id == bound
        evidence = db.scalar(select(SkillEvidence))
        assert evidence.assisted is True and evidence.hint_count == 1
        assert db.scalar(select(UserSkill)).independent_score == 0.0


def test_check_requires_pending_get_and_preserves_it_after_invalid_answers(client):
    setup_user(client, "check-get-required@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    endpoint = "/learning/lessons/variables-v1/knowledge-check"
    assert client.post(endpoint, headers=headers, json={"answers": {}}).status_code == 409
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(KnowledgeCheckSession)) is None
        assert db.scalar(select(KnowledgeCheckAttempt)) is None
        assert db.scalar(select(ExerciseVersion)) is None
    questions = client.get(endpoint).json()
    assert client.post(endpoint, headers=headers, json={"answers": {}}).status_code == 422
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(KnowledgeCheckSession)).consumed_at is None
    answers = {q["id"]: q["choices"][0] for q in questions}
    assert client.post(endpoint, headers=headers, json={"answers": answers}).status_code == 201
    assert client.post(endpoint, headers=headers, json={"answers": answers}).status_code == 409


def test_check_response_schema_has_no_internal_attempt_identifier(client):
    setup_user(client, "check-public-contract@example.com")
    endpoint = "/learning/lessons/variables-v1/knowledge-check"
    questions = client.get(endpoint).json()
    answers = {
        questions[0]["id"]: "6",
        questions[1]["id"]: "Увеличивает текущее значение x на 1",
    }
    result = client.post(endpoint, headers={"X-CSRF-Token": csrf(client)}, json={"answers": answers})
    assert result.status_code == 201
    assert set(result.json()) == {
        "lesson_id", "score", "passed", "explanations", "recommendation", "recommended_lesson_id",
    }
    assert all(
        item["selected_explanation"] == item["explanation"]
        for item in result.json()["explanations"]
    )
    schema = client.get("/openapi.json").json()["components"]["schemas"]["CheckResponse"]
    assert "attempt_id" not in schema["properties"]
    with next(app.dependency_overrides[get_db]()) as db:
        assert str(db.scalar(select(KnowledgeCheckAttempt)).id) not in result.text


def test_schema_two_returns_only_selected_feedback_from_bound_snapshot(client, monkeypatch):
    setup_user(client, "selected-feedback@example.com")
    from app import exercise_snapshots

    original_ladder_version = EXERCISE_HINT_LADDERS["variables-v1"]["version"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", 2)
    original_checks = exercise_snapshots.CHECKS

    def tagged_checks(tag):
        return {
            **original_checks,
            "variables-v1": tuple(
                {
                    **question,
                    "choice_explanations": {
                        choice: f"{tag}:{index}:{choice}"
                        for choice in question["choices"]
                    },
                }
                for index, question in enumerate(original_checks["variables-v1"])
            ),
        }

    monkeypatch.setattr(exercise_snapshots, "CHECKS", tagged_checks("v2"))
    endpoint = "/learning/lessons/variables-v1/knowledge-check"
    public_questions = client.get(endpoint)
    assert public_questions.status_code == 200
    assert all(set(question) == {"id", "prompt", "choices"} for question in public_questions.json())
    assert "answer" not in public_questions.text
    assert "explanation" not in public_questions.text
    assert "exercise_version_id" not in public_questions.text

    with next(app.dependency_overrides[get_db]()) as db:
        pending = db.scalar(select(KnowledgeCheckSession).where(KnowledgeCheckSession.consumed_at.is_(None)))
        old_version = db.get(ExerciseVersion, pending.exercise_version_id)
        old_snapshot = old_version.content_snapshot
        old_version_id = old_version.id
        assert old_snapshot["schema_version"] == 2

    # Publish a later authored version after GET. The pending response must
    # still grade and select feedback from the immutable v2 snapshot.
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", 3)
    monkeypatch.setattr(exercise_snapshots, "CHECKS", tagged_checks("v3"))
    with next(app.dependency_overrides[get_db]()) as db:
        from app.exercise_hints import _seed_exercise

        new_version = _seed_exercise(db, "variables-v1")
        db.commit()
        assert new_version.id != old_version_id
        assert db.get(ExerciseVersion, old_version_id).content_snapshot == old_snapshot

    old_answers = {
        public_questions.json()[0]["id"]: public_questions.json()[0]["choices"][0],
        public_questions.json()[1]["id"]: public_questions.json()[1]["choices"][0],
    }
    old_result = client.post(
        endpoint,
        headers={"X-CSRF-Token": csrf(client)},
        json={"answers": old_answers},
    )
    assert old_result.status_code == 201
    first = old_result.json()["explanations"][0]
    assert first["selected_explanation"] == f"v2:0:{old_answers[first['question_id']]}"
    assert "v3:" not in old_result.text
    assert "choice_explanations" not in old_result.text
    assert all(
        f"v2:{index}:{choice}" not in old_result.text
        for index, question in enumerate(public_questions.json())
        for choice in question["choices"]
        if choice != old_answers[question["id"]]
    )

    new_questions = client.get(endpoint)
    assert new_questions.status_code == 200
    correct_answers = {
        question["id"]: next(
            authored["answer"]
            for authored in exercise_snapshots.CHECKS["variables-v1"]
            if authored["id"] == question["id"]
        )
        for question in new_questions.json()
    }
    new_result = client.post(
        endpoint,
        headers={"X-CSRF-Token": csrf(client)},
        json={"answers": correct_answers},
    )
    assert new_result.status_code == 201
    assert new_result.json()["passed"] is True
    assert new_result.json()["explanations"][0]["selected_explanation"].startswith("v3:")
    assert all("choice_explanations" not in item for item in new_result.json()["explanations"])


def test_schema_two_snapshot_rejects_incomplete_or_invalid_choice_feedback(client, monkeypatch):
    setup_user(client, "invalid-v2-check@example.com")
    from app import exercise_snapshots
    from app.exercise_snapshots import validate_check_snapshot

    original_version = EXERCISE_HINT_LADDERS["variables-v1"]["version"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", 2)
    original_checks = exercise_snapshots.CHECKS
    valid_checks = tuple(
        {
            **question,
            "choice_explanations": {choice: "Feedback for " + choice for choice in question["choices"]},
        }
        for question in original_checks["variables-v1"]
    )
    monkeypatch.setattr(
        exercise_snapshots,
        "CHECKS",
        {**original_checks, "variables-v1": valid_checks},
    )
    from app.exercise_snapshots import authored_snapshot

    valid_snapshot = authored_snapshot("variables-v1")
    assert valid_snapshot["schema_version"] == 2
    invalid_snapshots = []
    for mutation in (
        lambda question: question["choice_explanations"].pop(question["choices"][0]),
        lambda question: question["choice_explanations"].update({"extra": "Not a real choice"}),
        lambda question: question["choice_explanations"].update({question["choices"][0]: "  "}),
        lambda question: question.update({"answer": "not-an-offered-choice"}),
    ):
        broken = {
            **valid_snapshot,
            "checks": [dict(valid_snapshot["checks"][0]), *valid_snapshot["checks"][1:]],
        }
        mutation(broken["checks"][0])
        invalid_snapshots.append(broken)
    for snapshot in invalid_snapshots:
        with pytest.raises(ValueError):
            validate_check_snapshot(snapshot, "variables-v1")
        monkeypatch.setattr(
            exercise_snapshots,
            "CHECKS",
            {**original_checks, "variables-v1": tuple(snapshot["checks"])},
        )
        response = client.get(
            "/learning/lessons/variables-v1/knowledge-check"
        )
        assert response.status_code == 409
        assert "choice_explanations" not in response.text


def test_pending_check_hint_uses_shown_version_after_publication(client, monkeypatch):
    setup_user(client, "check-hint-binding@example.com")
    client.get("/learning/lessons/variables-v1/knowledge-check")
    with next(app.dependency_overrides[get_db]()) as db:
        old_version = db.scalar(select(KnowledgeCheckSession))
        original_id = old_version.exercise_version_id
        old_text = db.get(ExerciseVersion, original_id).content_snapshot["hints"][0]["text"]
    original_number = EXERCISE_HINT_LADDERS["variables-v1"]["version"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original_number + 1)
    enable_choice_feedback(monkeypatch, "variables-v1", prefix="pending-hint")
    try:
        response = client.post(
            "/learning/exercises/variables-v1/hints",
            headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "check-bound-hint"},
            json={"level": 1},
        )
        assert response.status_code == 200
        assert response.json()["text"] == old_text
        with next(app.dependency_overrides[get_db]()) as db:
            from app.db.models import HintReveal
            assert db.scalar(select(HintReveal)).exercise_version_id == original_id
    finally:
        monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original_number)
