import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client():
    from app.auth import _attempts
    _attempts.clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def csrf(client: TestClient) -> str:
    return client.cookies.get("mentor_csrf") or ""


def test_register_uses_opaque_cookies_and_requires_onboarding(client: TestClient):
    response = client.post("/auth/register", json={"email": " Learner@Example.com ", "password": "safe-password"})
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "learner@example.com"
    assert response.json()["onboarding_required"] is True
    assert "password" not in response.text
    assert client.cookies.get("mentor_session")
    assert client.cookies.get("mentor_csrf")

    assert client.get("/me").status_code == 200
    assert client.post("/onboarding", json={"experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180}).status_code == 403

    response = client.post("/onboarding", headers={"X-CSRF-Token": csrf(client)}, json={"experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180})
    assert response.status_code == 200
    assert response.json()["completed"] is True
    assert client.get("/me").json()["goal"]["target_role"] == "Python Backend"


def test_login_logout_and_invalid_password(client: TestClient):
    assert client.post("/auth/register", json={"email": "user@example.com", "password": "safe-password"}).status_code == 201
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    assert client.get("/me").status_code == 401

    response = client.post("/auth/login", json={"email": "USER@example.com", "password": "wrong-password"})
    assert response.status_code == 401
    response = client.post("/auth/login", json={"email": "USER@example.com", "password": "safe-password"})
    assert response.status_code == 200
    assert response.json()["onboarding_required"] is True


def test_profile_update_is_csrf_protected(client: TestClient):
    assert client.post("/auth/register", json={"email": "profile@example.com", "password": "safe-password"}).status_code == 201
    response = client.patch("/me/profile", json={"display_name": "Learner"})
    assert response.status_code == 403
    response = client.patch("/me/profile", headers={"X-CSRF-Token": csrf(client)}, json={"display_name": "Learner", "experience_level": "student"})
    assert response.status_code == 200
    assert response.json()["profile"]["display_name"] == "Learner"
