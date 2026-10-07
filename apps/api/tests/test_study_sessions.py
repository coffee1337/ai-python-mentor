"""Presence timers persist independently from learning and recommendations."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import study_sessions
from app.account_services import throttle_key, utcnow
from app.db.account_models import AuthThrottle
from app.db.base import Base
from app.db.models import CurriculumSession, SkillEvidence, User
from app.db.session import get_db
from app.db.study_session_models import StudySession
from app.main import app
from test_auth import client, csrf

NOW = datetime(2026, 10, 7, 9, tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    value = [NOW]
    monkeypatch.setattr(study_sessions, "_utc_now", lambda: value[0])
    return value


def database():
    return next(app.dependency_overrides[get_db]())


def setup_user(c, email="timer@example.com"):
    response = c.post("/auth/register", json={"email": email, "password": "safe-password"})
    assert response.status_code == 201
    user_id = UUID(response.json()["user"]["id"])
    assert post(c, "/onboarding", {"experience_level": "beginner", "target_role": "Python Backend",
                                 "weekly_minutes": 180}).status_code == 200
    return user_id


def scope_headers(c):
    scope = c.get("/me").json().get("account_scope")
    return {"X-Account-Scope": scope} if scope else {}


def get(c, path):
    return c.get(path, headers=scope_headers(c))


def post(c, path, payload):
    return c.post(path, headers={"X-CSRF-Token": csrf(c), **scope_headers(c)}, json=payload)


def start(c):
    response = post(c, "/learning/study-sessions/start", {})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def action(c, body, kind):
    return post(c, f"/learning/study-sessions/{body['id']}/{kind}", {"expected_revision": body["revision"]})


def stored(session_id):
    with database() as db:
        row = db.get(StudySession, UUID(session_id))
        return {name: getattr(row, name) for name in ("status", "revision", "updated_at", "last_activity_at",
                                                     "accumulated_milliseconds", "ended_at", "focus_snapshot")}


def business_counts(db):
    return {table.name: db.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables if table.name not in {"study_sessions", "auth_throttle"}}


def test_auth_onboarding_csrf_and_strict_input(client, clock):
    for path in ("/learning/study-session", "/learning/study-sessions"):
        assert get(client, path).status_code == 401
    assert post(client, "/learning/study-sessions/start", {}).status_code == 401
    client.post("/auth/register", json={"email": "timer@example.com", "password": "safe-password"})
    assert get(client, "/learning/study-session").status_code == 409
    assert post(client, "/learning/study-sessions/start", {}).status_code == 409
    post(client, "/onboarding", {"experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180})
    assert client.post("/learning/study-sessions/start", json={}).status_code == 403
    for payload in ({"active_seconds": 1000}, {"focus": []}, {"user_id": str(uuid4())}, {"started_at": NOW.isoformat()}):
        assert post(client, "/learning/study-sessions/start", payload).status_code == 422
    run = start(client)
    for value in (0, -1, True, "1", 1.5, 2147483647, 99999999999999999999):
        assert post(client, f"/learning/study-sessions/{run['id']}/pause", {"expected_revision": value}).status_code == 422
    assert post(client, f"/learning/study-sessions/{run['id']}/pause",
                {"expected_revision": 1, "active_seconds": 30}).status_code == 422
    assert client.post(f"/learning/study-sessions/{run['id']}/pause", json={"expected_revision": 1}).status_code == 403
    for limit in (0, 51):
        assert get(client, f"/learning/study-sessions?limit={limit}").status_code == 422


def test_start_snapshots_public_focus_and_is_idempotent_without_credit(client, clock):
    setup_user(client)
    with database() as db:
        before = business_counts(db)
    assert get(client, "/learning/study-session").json() == {"session": None}
    run = start(client)
    assert run["status"] == "active" and run["active_seconds"] == 0 and run["revision"] == 1
    assert run["focus"][0]["lesson_id"] == "variables-v2"
    assert run["estimated_minutes"] > 0 and run["target_minutes"] == 60 and run["idle_timeout_seconds"] == 60
    clock[0] += timedelta(seconds=12)
    repeated = start(client)
    assert repeated["id"] == run["id"] and repeated["revision"] == 1 and repeated["active_seconds"] == 12
    assert len(get(client, "/learning/study-sessions").json()) == 1
    for private in ("user_id", "answer", "exercise_version_id", "hint", "snapshot", "source_code", "last_activity_at"):
        assert private not in run
    with database() as db:
        assert business_counts(db) == before
        assert db.scalar(select(func.count()).select_from(SkillEvidence)) == 0
        assert db.scalar(select(func.count()).select_from(CurriculumSession)) == 0


def test_heartbeat_preserves_fractional_seconds_and_pause_resume_finish(client, clock):
    setup_user(client)
    run = start(client)
    clock[0] += timedelta(seconds=20, milliseconds=600)
    run = action(client, run, "heartbeat").json()
    assert run["active_seconds"] == 20 and run["revision"] == 2
    clock[0] += timedelta(seconds=20, milliseconds=600)
    run = action(client, run, "pause").json()
    assert run["status"] == "paused" and run["active_seconds"] == 41
    clock[0] += timedelta(hours=4)
    assert get(client, "/learning/study-session").json()["session"]["active_seconds"] == 41
    assert action(client, run, "heartbeat").status_code == 409
    run = action(client, run, "resume").json()
    assert run["status"] == "active" and run["active_seconds"] == 41
    clock[0] += timedelta(seconds=10)
    run = action(client, run, "finish").json()
    assert run["status"] == "completed" and run["active_seconds"] == 51
    assert run["ended_at"] == clock[0].isoformat().replace("+00:00", "Z")
    assert get(client, "/learning/study-session").json() == {"session": None}
    clock[0] += timedelta(hours=8)
    assert get(client, "/learning/study-sessions").json()[0]["active_seconds"] == 51
    for kind in ("pause", "resume", "heartbeat", "finish", "abandon"):
        assert action(client, run, kind).status_code == 409


def test_expired_read_is_paused_readonly_start_does_not_renew_and_resume_is_explicit(client, clock):
    setup_user(client)
    run = start(client)
    before = stored(run["id"])
    clock[0] += timedelta(hours=2)
    response = get(client, "/learning/study-session")
    assert response.headers["cache-control"] == "no-store"
    projected = response.json()["session"]
    assert projected["status"] == "paused" and projected["active_seconds"] == 60 and projected["revision"] == 1
    assert get(client, "/learning/study-sessions").json()[0]["status"] == "paused"
    assert start(client)["status"] == "paused"
    assert stored(run["id"]) == before
    assert action(client, projected, "heartbeat").status_code == 409
    assert stored(run["id"]) == before
    resumed = action(client, projected, "resume").json()
    assert resumed["status"] == "active" and resumed["active_seconds"] == 60 and resumed["revision"] == 2
    clock[0] += timedelta(seconds=15)
    finished = action(client, resumed, "finish").json()
    assert finished["active_seconds"] == 75


def test_backward_clock_cannot_recount_a_closed_segment(client, clock):
    setup_user(client)
    run = start(client)
    clock[0] += timedelta(seconds=20)
    run = action(client, run, "heartbeat").json()
    clock[0] -= timedelta(seconds=10)
    run = action(client, run, "heartbeat").json()
    assert run["active_seconds"] == 20
    assert stored(run["id"])["last_activity_at"] == (NOW + timedelta(seconds=20)).replace(tzinfo=None)
    clock[0] = NOW + timedelta(seconds=25)
    assert action(client, run, "finish").json()["active_seconds"] == 25


def test_durable_timer_admission_bounds_mutations_without_blocking_normal_heartbeat(client, clock):
    owner_id = setup_user(client)
    run = start(client)
    key = throttle_key("study_session_user", str(owner_id))
    with database() as db:
        bucket = db.get(AuthThrottle, key)
        bucket.attempts = 60
        bucket.window_start = utcnow()
        db.commit()
    assert action(client, run, "finish").status_code == 429
    assert post(client, "/learning/study-sessions/start", {}).status_code == 429
    clock[0] += timedelta(seconds=20)
    assert action(client, run, "heartbeat").status_code == 200
    with database() as db:
        heartbeat_bucket = db.get(AuthThrottle, throttle_key("study_session_heartbeat", str(owner_id)))
        heartbeat_bucket.attempts = 120
        heartbeat_bucket.window_start = utcnow()
        db.commit()
    current = get(client, "/learning/study-session").json()["session"]
    assert action(client, current, "heartbeat").status_code == 429


def test_account_scope_rejects_stale_tab_before_any_timer_mutation(client, clock):
    owner_id = setup_user(client)
    run = start(client)
    old_scope = scope_headers(client)["X-Account-Scope"]
    second_id = setup_user(client, "second-timer@example.com")
    assert scope_headers(client)["X-Account-Scope"] != old_scope
    stale_headers = {"X-Account-Scope": old_scope, "X-CSRF-Token": csrf(client)}
    for path in ("/learning/study-session", "/learning/study-sessions"):
        assert client.get(path).status_code == 409
        response = client.get(path, headers=stale_headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "account_changed"
    assert client.post("/learning/study-sessions/start", headers=stale_headers, json={}).status_code == 409
    assert client.post("/learning/study-sessions/start", headers={"X-CSRF-Token": csrf(client)}, json={}).status_code == 409
    for kind in ("pause", "resume", "heartbeat", "finish", "abandon"):
        response = client.post(f"/learning/study-sessions/{run['id']}/{kind}",
                               headers=stale_headers, json={"expected_revision": 1})
        assert response.status_code == 409
    with database() as db:
        assert db.scalar(select(func.count()).select_from(StudySession).where(StudySession.user_id == second_id)) == 0
        owner_run = db.get(StudySession, UUID(run["id"]))
        assert owner_run.user_id == owner_id and owner_run.status == "active" and owner_run.revision == 1


@pytest.mark.parametrize("kind,status", [("pause", "paused"), ("finish", "completed"), ("abandon", "abandoned")])
def test_expired_actions_count_last_lease_only_once(client, clock, kind, status):
    setup_user(client)
    run = start(client)
    clock[0] += timedelta(days=2)
    response = action(client, run, kind)
    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == status and updated["active_seconds"] == 60
    assert stored(run["id"])["accumulated_milliseconds"] == 60000
    clock[0] += timedelta(days=2)
    assert get(client, "/learning/study-sessions").json()[0]["active_seconds"] == 60


def test_lease_boundary_cap_and_stale_revision_are_controlled(client, clock):
    setup_user(client)
    run = start(client)
    clock[0] += timedelta(seconds=60)
    assert action(client, run, "heartbeat").status_code == 409
    resumed = action(client, run, "resume").json()
    assert resumed["active_seconds"] == 60
    assert action(client, run, "finish").status_code == 409
    assert stored(run["id"])["revision"] == 2
    with database() as db:
        row = db.get(StudySession, UUID(run["id"]))
        row.accumulated_milliseconds = study_sessions.MAX_ACTIVE_SECONDS * 1000 - 10000
        db.commit()
    before = stored(run["id"])
    clock[0] += timedelta(seconds=20)
    projected = get(client, "/learning/study-session").json()["session"]
    assert projected["status"] == "paused" and projected["active_seconds"] == 28800
    assert stored(run["id"]) == before
    assert action(client, projected, "heartbeat").status_code == 409
    assert action(client, projected, "resume").status_code == 409
    assert action(client, projected, "finish").json()["active_seconds"] == 28800


def test_single_open_unique_constraint_allows_completed_history(client, clock):
    owner_id = setup_user(client)
    run = start(client)
    with database() as db:
        original = db.get(StudySession, UUID(run["id"]))
        db.add(StudySession(user_id=owner_id, status="paused", revision=1, started_at=NOW,
            updated_at=NOW, accumulated_milliseconds=0, focus_snapshot=original.focus_snapshot,
            estimated_minutes=1, target_minutes=60))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    assert action(client, run, "finish").status_code == 200
    newer = start(client)
    assert newer["id"] != run["id"]
    assert len(get(client, "/learning/study-sessions").json()) == 2


def test_no_focus_rejects_start_without_timer_or_learning_write(client, clock, monkeypatch):
    setup_user(client)
    response = study_sessions.TodayResponse.model_validate({"schema_version": 1, "as_of": NOW,
        "next_lesson": None, "due_reviews": [], "focus": [], "estimated_minutes": 0,
        "target_minutes": 60, "source": "course"})
    monkeypatch.setattr(study_sessions, "today", lambda **kwargs: response)
    with database() as db:
        before = business_counts(db)
    assert post(client, "/learning/study-sessions/start", {}).status_code == 409
    assert get(client, "/learning/study-session").json() == {"session": None}
    with database() as db:
        assert business_counts(db) == before


def test_history_is_bounded_owned_and_export_delete_follow_owner(client, clock):
    owner_id = setup_user(client)
    run = start(client)
    with database() as db:
        other = User(email="foreign-timer@example.com", password_hash="unused")
        db.add(other)
        db.flush()
        foreign = StudySession(user_id=other.id, status="paused", revision=1, started_at=NOW,
            updated_at=NOW, accumulated_milliseconds=123000, focus_snapshot=[], estimated_minutes=0, target_minutes=10)
        db.add(foreign)
        for index in range(52):
            stamp = NOW - timedelta(minutes=index + 1)
            db.add(StudySession(user_id=owner_id, status="completed", revision=2, started_at=stamp,
                updated_at=stamp, ended_at=stamp, accumulated_milliseconds=20000,
                focus_snapshot=[], estimated_minutes=0, target_minutes=10))
        db.commit()
        foreign_id = str(foreign.id)
    for kind in ("pause", "resume", "heartbeat", "finish", "abandon"):
        assert action(client, {"id": foreign_id, "revision": 1}, kind).status_code == 404
        assert action(client, {"id": str(uuid4()), "revision": 1}, kind).status_code == 404
    history = get(client, "/learning/study-sessions?limit=50")
    assert history.headers["cache-control"] == "no-store"
    assert len(history.json()) == 50 and history.json()[0]["id"] == run["id"]
    assert foreign_id not in history.text
    exported = get(client, "/me/export").json()["data"]["study_sessions"]
    assert len(exported) == 53 and all(row["user_id"] == str(owner_id) for row in exported)
    assert post(client, "/me/delete", {"password": "safe-password", "confirmation": "DELETE"}).status_code == 204
    with database() as db:
        assert db.scalar(select(func.count()).select_from(StudySession).where(StudySession.user_id == owner_id)) == 0
        assert db.get(StudySession, UUID(foreign_id)) is not None
