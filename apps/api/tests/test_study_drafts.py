"""Private drafts preserve concurrent work without creating learning results."""
from datetime import datetime, timezone
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app import study_drafts
from app.db.base import Base
from app.db.models import CodingAttempt, ExerciseVersion, KnowledgeCheckSession, LessonSession, User, UserSkill
from app.db.session import get_db
from app.db.study_draft_models import StudyDraft
from app.exercise_hints import _seed_exercise
from app.main import app
from app.skill_graph import SKILLS
from test_auth import client, csrf


def database():
    return next(app.dependency_overrides[get_db]())


def setup(c, email="drafts@example.com"):
    response = c.post("/auth/register", json={"email": email, "password": "safe-password"})
    assert response.status_code == 201
    assert c.post("/onboarding", headers={"X-CSRF-Token": csrf(c)}, json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180,
    }).status_code == 200
    return UUID(response.json()["user"]["id"])


def lesson(c, kind="lesson_flow", *, checks=True):
    response = c.get("/learning/next")
    assert response.status_code == 200
    value = response.json()
    identity = {"kind": kind, "resource_id": value["id"], "version": int(value["version"]), "milestone_id": ""}
    questions = []
    if checks:
        response = c.get(f"/learning/lessons/{value['id']}/knowledge-check")
        assert response.status_code == 200
        questions = response.json()
    return identity, questions


def save(c, identity, content, revision=0, **extra):
    return c.post("/learning/drafts", headers={"X-CSRF-Token": csrf(c), **scope_headers(c)}, json={
        "identity": identity, "expected_revision": revision, "content": content, **extra,
    })


def read(c, identity):
    return c.get("/learning/drafts", params=identity, headers=scope_headers(c))


def scope_headers(c):
    scope = c.get("/me").json().get("account_scope")
    return {"X-Account-Scope": scope} if scope else {}


def project(c):
    template = c.get("/projects/templates").json()[0]
    response = c.post("/projects", headers={"X-CSRF-Token": csrf(c)}, json={"template_id": template["id"]})
    assert response.status_code == 201
    value = response.json()
    return {"kind": "project_milestone", "resource_id": value["id"], "version": 0, "milestone_id": value["milestones"][0]["id"]}


def coding(c, monkeypatch):
    monkeypatch.setenv("EXECUTION_JOBS_ENABLED", "false")
    response = c.post("/learning/exercises/variables-v1-code/jobs", headers={
        "X-CSRF-Token": csrf(c), "Idempotency-Key": str(uuid4()),
    }, json={"language": "python", "mode": "function", "source_code": "def solve(p): return 0"})
    assert response.status_code == 202
    with database() as db:
        attempt = db.get(CodingAttempt, UUID(response.json()["attempt_id"]))
        version = db.get(ExerciseVersion, attempt.exercise_version_id)
        return {"kind": "coding", "resource_id": attempt.exercise_id, "version": version.version, "milestone_id": ""}


def business_state():
    names = (
        "exercise_versions", "lesson_sessions", "knowledge_check_sessions", "lesson_completions",
        "knowledge_check_attempts", "knowledge_check_responses", "coding_attempts", "execution_jobs",
        "skill_evidence", "user_skills", "hint_reveals", "project_submissions", "lesson_reflections",
    )
    with database() as db:
        return {name: [dict(row) for row in db.execute(select(Base.metadata.tables[name])).mappings()] for name in names}


def test_auth_csrf_onboarding_and_absent_read_are_safe(client):
    identity = {"kind": "reflection", "resource_id": "variables-v2", "version": 1, "milestone_id": ""}
    assert read(client, identity).status_code == 401
    assert save(client, identity, {"text": "private"}).status_code == 401
    assert client.post("/auth/register", json={"email": "drafts@example.com", "password": "safe-password"}).status_code == 201
    assert read(client, identity).status_code == 409
    client.post("/onboarding", headers={"X-CSRF-Token": csrf(client)}, json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180,
    })
    identity, _ = lesson(client, "reflection", checks=False)
    before = business_state()
    response = read(client, identity)
    assert response.status_code == 200
    assert response.json() == {"identity": identity, "revision": 0, "content": None, "updated_at": None}
    assert response.headers["Cache-Control"] == "no-store"
    assert client.post("/learning/drafts", json={"identity": identity, "expected_revision": 0, "content": {"text": "hello"}}).status_code == 403
    with database() as db:
        assert db.scalar(select(func.count()).select_from(StudyDraft)) == 0
    assert business_state() == before


def test_exact_utf8_saved_across_login_and_no_private_version_fields(client):
    setup(client)
    identity, _ = lesson(client, "reflection")
    content = {"text": "  Разбор 🐍\r\n<script>не выполнять</script>\n  "}
    response = save(client, identity, content)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    value = response.json()
    assert set(value) == {"identity", "revision", "content", "updated_at"}
    assert value["content"] == content and value["revision"] == 1
    assert "exercise_version_id" not in response.text and "answer" not in response.text
    assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)}).status_code == 204
    assert client.post("/auth/login", json={"email": "drafts@example.com", "password": "safe-password"}).status_code == 200
    assert read(client, identity).json() == value


def test_stale_variants_and_clears_cannot_overwrite_or_resurrect(client):
    setup(client)
    identity, _ = lesson(client, "reflection")
    first = save(client, identity, {"text": "device A"}).json()
    stale = save(client, identity, {"text": "device B"}, revision=0)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "draft_conflict"
    assert stale.json()["detail"]["current_revision"] == 1
    assert "device A" not in stale.text and "device B" not in stale.text
    assert stale.headers["Cache-Control"] == "no-store"
    assert read(client, identity).json() == first
    # Even an identical stale retry is a conflict, allowing the UI to compare
    # the separately fetched owner-only server variant explicitly.
    assert save(client, identity, {"text": "device A"}, revision=0).status_code == 409
    cleared = save(client, identity, None, revision=1)
    assert cleared.status_code == 200 and cleared.json()["revision"] == 2
    assert cleared.json()["content"] is None
    assert save(client, identity, {"text": "late offline upload"}, revision=1).status_code == 409
    assert save(client, identity, {"text": "late new draft"}, revision=0).status_code == 409
    assert read(client, identity).json()["revision"] == 2
    assert save(client, identity, {"text": "conscious replacement"}, revision=2).json()["revision"] == 3


def test_required_account_scope_blocks_old_tab_after_shared_cookies_change(client):
    owner = setup(client)
    identity, _ = lesson(client, "reflection")
    scope_a = scope_headers(client)
    assert save(client, identity, {"text": "A's private draft"}).status_code == 200
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    other = setup(client, "shared-cookie-other@example.com")
    same_identity, _ = lesson(client, "reflection")
    assert same_identity == identity
    before = business_state()
    with database() as db:
        before_drafts = [dict(row) for row in db.execute(select(StudyDraft.__table__)).mappings()]
    for headers in (scope_a, {}):
        rejected_read = client.get("/learning/drafts", params=identity, headers=headers)
        rejected_save = client.post("/learning/drafts", headers={"X-CSRF-Token": csrf(client), **headers}, json={
            "identity": identity, "expected_revision": 0, "content": {"text": "A's unsent work must not enter B's account"},
        })
        for response in (rejected_read, rejected_save):
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "account_changed"
            assert response.headers["Cache-Control"] == "no-store"
            assert "A's" not in response.text
    with database() as db:
        assert [dict(row) for row in db.execute(select(StudyDraft.__table__)).mappings()] == before_drafts
        assert db.scalar(select(func.count()).select_from(StudyDraft).where(StudyDraft.user_id == other)) == 0
        assert db.scalar(select(func.count()).select_from(StudyDraft).where(StudyDraft.user_id == owner)) == 1
    assert business_state() == before
    assert read(client, identity).json()["revision"] == 0
    assert save(client, identity, {"text": "B's conscious new draft"}).status_code == 200


def test_password_rotation_invalidates_retained_account_scope(client):
    setup(client)
    identity, _ = lesson(client, "reflection")
    old_scope = scope_headers(client)
    assert save(client, identity, {"text": "retained work"}).status_code == 200
    response = client.post("/me/password", headers={"X-CSRF-Token": csrf(client)}, json={
        "current_password": "safe-password", "password": "new-safe-password",
    })
    assert response.status_code == 200
    # The existing password-change contract revokes all sessions. Establish the
    # new authenticated session before isolating the old scope precondition.
    assert client.get("/me").status_code == 401
    assert client.post("/auth/login", json={"email": "drafts@example.com", "password": "new-safe-password"}).status_code == 200
    assert scope_headers(client) != old_scope
    response = client.get("/learning/drafts", params=identity, headers=old_scope)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "account_changed"
    assert read(client, identity).json()["content"] == {"text": "retained work"}


def test_flow_restores_only_ungraded_choices_of_exact_pending_snapshot(client):
    setup(client)
    identity, questions = lesson(client)
    content = {"step": 2, "answers": {questions[0]["id"]: questions[0]["choices"][0]}}
    before = business_state()
    response = save(client, identity, content)
    assert response.status_code == 200 and response.json()["content"] == content
    for bad in (
        {"step": 2, "answers": {"unpublished-question": "bad"}},
        {"step": 2, "answers": {questions[0]["id"]: "unknown-choice"}},
        {"step": 2, "answers": {}, "correct": True},
        {"step": True, "answers": {}},
    ):
        assert save(client, identity, bad, revision=1).status_code == 422
    assert business_state() == before
    with database() as db:
        pending = db.scalar(select(KnowledgeCheckSession).where(KnowledgeCheckSession.lesson_id == identity["resource_id"]))
        pending.consumed_at = datetime.now(timezone.utc)
        db.commit()
    assert save(client, identity, content, revision=1).status_code == 409
    assert save(client, identity, {"step": 3, "answers": {}}, revision=1).status_code == 200


def test_other_owner_cannot_read_or_mutate_existing_drafts(client):
    setup(client)
    identity, _ = lesson(client, "reflection")
    project_identity = project(client)
    assert save(client, identity, {"text": "owner secret"}).status_code == 200
    assert save(client, project_identity, {"artifact_text": "private code", "repository_url": ""}).status_code == 200
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    setup(client, "other-drafts@example.com")
    assert read(client, identity).status_code == 404
    assert save(client, identity, {"text": "foreign overwrite"}, revision=1).status_code == 409
    assert read(client, project_identity).status_code == 404
    assert save(client, project_identity, {"artifact_text": "foreign overwrite", "repository_url": ""}).status_code == 404
    # After independently opening the shared lesson, the second owner sees an
    # empty private draft rather than the first learner's same public identity.
    own_identity, _ = lesson(client, "reflection")
    assert own_identity == identity
    assert read(client, identity).json()["revision"] == 0
    assert save(client, identity, {"text": "second owner's draft"}).status_code == 200
    with database() as db:
        assert db.scalar(select(func.count()).select_from(StudyDraft)) == 3


def test_unknown_version_and_identity_shapes_do_not_publish(client):
    setup(client)
    identity, _ = lesson(client, "reflection")
    before = business_state()
    for bad, status in (
        ({**identity, "version": 999}, 404),
        ({**identity, "resource_id": "never-published-v1"}, 404),
        ({**identity, "version": 0}, 422),
        ({**identity, "milestone_id": "other-stage"}, 422),
        ({**identity, "version": True}, 422),
        ({**identity, "kind": "assessment"}, 422),
    ):
        assert save(client, bad, {"text": "unfinished"}).status_code == status
    assert save(client, identity, {"text": "unfinished"}, user_id=str(uuid4())).status_code == 422
    assert business_state() == before


@pytest.mark.parametrize("kind,content", [
    ("reflection", {"text": "x" * 10001}),
    ("coding", {"source_code": "x" * 20001, "backup_source": None}),
    ("coding", {"source_code": "", "backup_source": "x" * 20001}),
    ("reflection", {"text": 17}),
])
def test_bounded_strict_content_does_not_echo_private_text(client, monkeypatch, kind, content):
    setup(client)
    if kind == "coding":
        identity = coding(client, monkeypatch)
    else:
        identity, _ = lesson(client, kind)
    response = save(client, identity, content)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_draft_content"
    assert "xxxxxxxx" not in response.text


def test_coding_draft_preserves_outgoing_backup_without_execution(client, monkeypatch):
    setup(client)
    identity = coding(client, monkeypatch)
    content = {"source_code": "  print('🐍')\n", "backup_source": "\r\nold draft\t"}
    before = business_state()
    assert save(client, identity, content).json()["content"] == content
    assert read(client, identity).json()["content"] == content
    assert business_state() == before


def test_first_coding_draft_requires_interface_readiness_and_opened_owned_lesson(client):
    owner = setup(client)
    # Exercise the existing explicit readiness fallback with test-only mastery
    # fixtures. The draft endpoint must not manufacture these observations.
    with database() as db:
        for skill in SKILLS:
            db.add(UserSkill(user_id=owner, skill_id=skill["id"], knowledge_score=1,
                practice_score=1, independent_score=1, evidence_count=1))
        db.commit()
    specification = client.get("/learning/exercises/dataclasses-v1/coding-specification")
    assert specification.status_code == 200
    spec = specification.json()
    identity = {"kind": "coding", "resource_id": spec["exercise_id"], "version": spec["version"], "milestone_id": ""}
    # Publishing the shared specification alone does not prove this owner
    # opened the lesson whose private draft is being synchronized.
    assert read(client, identity).status_code == 404
    assert client.get("/learning/lessons/dataclasses-v1").status_code == 200
    before = business_state()
    assert read(client, identity).json()["revision"] == 0
    content = {"source_code": spec["starter_code"] + "\n# unfinished", "backup_source": None}
    assert save(client, identity, content).status_code == 200
    assert business_state() == before
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    setup(client, "novice-coding-draft@example.com")
    assert read(client, identity).status_code == 404
    assert save(client, identity, content).status_code == 404


def test_first_coding_draft_supports_exact_owned_historical_resume(client):
    owner = setup(client)
    with database() as db:
        for skill in SKILLS:
            db.add(UserSkill(user_id=owner, skill_id=skill["id"], knowledge_score=1,
                practice_score=1, independent_score=1, evidence_count=1))
        version = _seed_exercise(db, "variables-v1", seed_hints=False)
        db.add(LessonSession(user_id=owner, lesson_id="variables-v1", exercise_version_id=version.id))
        db.commit()
    spec_response = client.get("/learning/exercises/variables-v1/coding-specification")
    assert spec_response.status_code == 200
    spec = spec_response.json()
    identity = {"kind": "coding", "resource_id": spec["exercise_id"], "version": spec["version"], "milestone_id": ""}
    before = business_state()
    assert read(client, identity).status_code == 200
    assert save(client, identity, {"source_code": "def solve(p):\n    pass", "backup_source": None}).status_code == 200
    assert business_state() == before


def test_coding_kind_rejects_lesson_snapshot_and_corrupt_identity_fails_closed(client):
    setup(client)
    identity, _ = lesson(client, "reflection")
    assert read(client, {**identity, "kind": "coding"}).status_code == 404
    assert save(client, identity, {"text": "private draft"}).status_code == 200
    with database() as db:
        version = db.scalar(select(ExerciseVersion).where(ExerciseVersion.exercise_id == identity["resource_id"], ExerciseVersion.version == identity["version"]))
        original = deepcopy(version.content_snapshot)
        version_id = version.id
    for invalid in (None, {**original, "schema_version": True}, {**original, "version": True}, {**original, "exercise_id": "foreign-snapshot"}):
        with database() as db:
            version = db.get(ExerciseVersion, version_id)
            version.content_snapshot = invalid
            db.commit()
        response = read(client, identity)
        assert response.status_code == 409 and "private draft" not in response.text


def test_flow_answers_cannot_bind_to_another_public_version(client):
    setup(client)
    identity, questions = lesson(client)
    with database() as db:
        old = db.scalar(select(ExerciseVersion).where(ExerciseVersion.exercise_id == identity["resource_id"], ExerciseVersion.version == identity["version"]))
        snapshot = deepcopy(old.content_snapshot)
        snapshot["version"] += 1
        changed = ExerciseVersion(exercise_id=old.exercise_id, version=old.version + 1, lesson_id=old.lesson_id, content_snapshot=snapshot)
        db.add(changed)
        db.flush()
        pending = db.scalar(select(KnowledgeCheckSession).where(KnowledgeCheckSession.lesson_id == identity["resource_id"]))
        pending.exercise_version_id = changed.id
        db.commit()
    assert save(client, identity, {"step": 2, "answers": {questions[0]["id"]: questions[0]["choices"][0]}}).status_code == 409
    assert save(client, identity, {"step": 1, "answers": {}}).status_code == 200


def test_project_context_content_and_delete_cleanup(client):
    setup(client)
    identity = project(client)
    content = {"artifact_text": "  Незавершённый код\r\n ", "repository_url": "unfinished URL"}
    assert save(client, identity, content).json()["content"] == content
    assert save(client, {**identity, "milestone_id": "missing-stage"}, content).status_code == 404
    assert save(client, identity, {**content, "artifact_text": "x" * 25001}, revision=1).status_code == 422
    assert client.delete(f"/projects/{identity['resource_id']}", headers={"X-CSRF-Token": csrf(client)}).status_code == 204
    assert read(client, identity).status_code == 404
    with database() as db:
        assert db.scalar(select(func.count()).select_from(StudyDraft)) == 0


def test_export_delete_include_private_drafts_and_clears_only_their_owner(client):
    owner = setup(client)
    identity, _ = lesson(client, "reflection")
    save(client, identity, {"text": "exported private reflection"})
    project_identity = project(client)
    save(client, project_identity, None)
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    other = setup(client, "second-drafts@example.com")
    second_identity, _ = lesson(client, "reflection")
    save(client, second_identity, {"text": "other private reflection"})
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    client.post("/auth/login", json={"email": "drafts@example.com", "password": "safe-password"})
    exported = client.get("/me/export")
    assert exported.status_code == 200
    assert "exported private reflection" in exported.text and "other private reflection" not in exported.text
    rows = exported.json()["data"]["study_drafts"]
    assert len(rows) == 2 and any(row["content"] is None and row["revision"] == 1 for row in rows)
    assert client.post("/me/delete", headers={"X-CSRF-Token": csrf(client)}, json={
        "password": "safe-password", "confirmation": "DELETE",
    }).status_code == 204
    with database() as db:
        assert db.get(User, owner) is None and db.get(User, other) is not None
        assert db.scalar(select(func.count()).select_from(StudyDraft).where(StudyDraft.user_id == owner)) == 0
        assert db.scalar(select(func.count()).select_from(StudyDraft).where(StudyDraft.user_id == other)) == 1


def test_quota_preserves_existing_work_and_tombstones(client, monkeypatch):
    setup(client)
    identity, _ = lesson(client, "reflection")
    monkeypatch.setattr(study_drafts, "MAX_IDENTITIES", 1)
    assert save(client, identity, None).status_code == 200
    second = {**identity, "kind": "lesson_flow"}
    response = save(client, second, {"step": 1, "answers": {}})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "draft_limit"
    assert read(client, identity).json()["revision"] == 1
    assert save(client, identity, {"text": "existing identity still works"}, revision=1).status_code == 200


def test_read_does_not_rebind_to_current_mutable_authored_content(client, monkeypatch):
    setup(client)
    identity, questions = lesson(client)
    content = {"step": 2, "answers": {questions[0]["id"]: questions[0]["choices"][0]}}
    assert save(client, identity, content).status_code == 200
    before = business_state()
    def fail(*args, **kwargs):
        pytest.fail("Draft recovery must not publish or authorize through a mutating resolver")
    monkeypatch.setattr("app.exercise_hints._seed_exercise", fail)
    monkeypatch.setattr("app.learning.accessible_lesson", fail)
    monkeypatch.setattr("app.coding_exercises.resolve_coding_exercise", fail)
    assert read(client, identity).json()["content"] == content
    assert save(client, identity, {"step": 3, "answers": {}}, revision=1).status_code == 200
    assert business_state() == before
