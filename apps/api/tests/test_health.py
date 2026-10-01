from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
import app.main as main


def test_health_returns_api_and_database_status(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement):
            assert str(statement) == "SELECT 1"

    monkeypatch.setattr(main.engine, "connect", lambda: Connection())
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_unavailable(monkeypatch):
    from sqlalchemy.exc import OperationalError

    def fail_connect():
        raise OperationalError("connect", {}, Exception("unavailable"))

    monkeypatch.setattr(main.engine, "connect", fail_connect)
    response = TestClient(app).get("/health")
    assert response.status_code == 503
    assert response.json()["detail"] == "Database is unavailable"
