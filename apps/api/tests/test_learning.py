from sqlalchemy import func, select

from app.db.models import LessonCompletion
from app.db.session import get_db
from app.main import app
from test_auth import client, csrf  # reuse the existing isolated database fixture


def register(client, email="learning@example.com"):
    assert client.post("/auth/register", json={"email": email, "password": "safe-password"}).status_code == 201


def onboard(client):
    assert client.post("/onboarding", headers={"X-CSRF-Token": csrf(client)}, json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180,
    }).status_code == 200


def complete(client, lesson="variables-v1", answer="6", **extra):
    return client.post(f"/learning/lessons/{lesson}/complete",
                       headers={"X-CSRF-Token": csrf(client)}, json={"answer": answer, **extra})


def test_auth_onboarding_csrf_and_validation(client):
    for path in ("/learning/path", "/learning/next", "/learning/lessons/variables-v1"):
        assert client.get(path).status_code == 401
    assert complete(client).status_code == 401
    register(client)
    assert client.get("/learning/path").status_code == 409
    assert complete(client).status_code == 409
    onboard(client)
    assert client.post("/learning/lessons/variables-v1/complete", json={"answer": "6"}).status_code == 403
    assert complete(client, user_id="another-user").status_code == 422
    assert complete(client, answer="__import__('os').system('echo unsafe')").status_code == 422
    assert complete(client, answer="x" * 201).status_code == 422
    assert complete(client, lesson="missing").status_code == 404
    assert client.get("/learning/lessons/missing").status_code == 404
    assert complete(client, lesson="conditions-v1", answer="adult").status_code == 409
    assert client.get("/learning/lessons/conditions-v1").status_code == 409


def test_full_flow_persists_and_is_idempotent(client):
    register(client)
    onboard(client)
    lesson = client.get("/learning/next").json()
    assert lesson["id"] == "variables-v1"
    assert "answer" not in lesson
    assert complete(client, answer="4").json()["path"]["completed"] == 0
    response = complete(client)
    assert response.json()["correct"] is True
    assert response.json()["path"]["next_lesson_id"] == "conditions-v1"
    stamp = response.json()["path"]["lessons"][0]["completed_at"]
    assert complete(client).json()["path"]["lessons"][0]["completed_at"] == stamp
    assert complete(client, answer="4").json()["path"]["completed"] == 1
    assert complete(client, lesson="conditions-v1", answer="adult").json()["path"]["completed"] == 2
    assert client.get("/learning/next").json() is None
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    assert client.post("/auth/login", json={"email": "learning@example.com", "password": "safe-password"}).status_code == 200
    assert client.get("/learning/path").json()["completed"] == 2
    assert client.get("/learning/lessons/variables-v1").status_code == 200
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(func.count()).select_from(LessonCompletion)) == 2
        assert db.scalar(select(LessonCompletion)).evidence_type == "authored_quiz_correct"


def test_progress_is_owned_by_session_user(client):
    register(client)
    onboard(client)
    complete(client)
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    register(client, "second@example.com")
    onboard(client)
    assert client.get("/learning/path").json()["completed"] == 0
    assert client.get("/learning/next").json()["id"] == "variables-v1"
    assert complete(client, lesson="conditions-v1", answer="adult").status_code == 409
    complete(client)
    assert client.get("/learning/path").json()["completed"] == 1
