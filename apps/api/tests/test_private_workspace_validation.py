"""Private outer-schema errors never reflect submitted source or extra values."""
from test_auth import client, csrf


def setup(client, email):
    assert client.post("/auth/register", json={"email": email, "password": "safe-password"}).status_code == 201
    headers = {"X-CSRF-Token": csrf(client)}
    assert client.post("/onboarding", headers=headers, json={"experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180}).status_code == 200
    headers["X-Account-Scope"] = client.get("/me").json()["account_scope"]
    return headers


def test_private_draft_outer_validation_redacts_input(client):
    headers = setup(client, "private-validation@example.com")
    marker = "UNSENT_PRIVATE_SOURCE_🐍"
    identity = {"kind": "reflection", "resource_id": "variables-v1", "version": 1, "milestone_id": ""}
    for payload in (
        {"identity": identity, "expected_revision": 0, "content": [marker]},
        {"identity": identity, "expected_revision": 0, "content": marker},
        {"identity": identity, "expected_revision": marker, "content": None},
        {"identity": identity, "expected_revision": 0, "content": None, marker: marker},
    ):
        response = client.post("/learning/drafts", headers=headers, json=payload)
        assert response.status_code == 422
        assert response.headers["Cache-Control"] == "no-store"
        assert marker not in response.text
        assert all(set(error) == {"loc", "type", "msg"} for error in response.json()["detail"])


def test_private_timer_validation_redacts_extra_input(client):
    headers = setup(client, "timer-validation@example.com")
    marker = "PRIVATE_EXTRA_TIMER_VALUE"
    response = client.post("/learning/study-sessions/start", headers=headers, json={marker: marker})
    assert response.status_code == 422 and marker not in response.text
    assert response.headers["Cache-Control"] == "no-store"


def test_guarded_existing_submission_rejects_changed_account(client):
    from sqlalchemy import func, select
    from app.db.reflection_models import LessonReflection
    from app.db.session import get_db
    from app.main import app

    first = setup(client, "first-stale-submission@example.com")
    first_lesson = client.get("/learning/next").json()["id"]
    assert client.post("/auth/logout", headers=first).status_code == 204
    second = setup(client, "second-stale-submission@example.com")
    assert client.get(f"/learning/lessons/{first_lesson}").status_code == 200
    marker = "PRIVATE_OLD_ACCOUNT_REFLECTION"
    response = client.post(f"/learning/lessons/{first_lesson}/reflections", headers={
        "X-CSRF-Token": second["X-CSRF-Token"], "X-Account-Scope": first["X-Account-Scope"],
        "Idempotency-Key": "old-tab-scope-guard",
    }, json={"text": marker})
    assert response.status_code == 409 and marker not in response.text
    assert response.json()["detail"]["code"] == "account_changed"
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(func.count()).select_from(LessonReflection)) == 0
