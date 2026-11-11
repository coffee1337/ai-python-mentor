"""Observability and layering invariants that the matrix claims but never proved.

Two claims lived only in prose: every response carries a correlation id that also
reaches the structured log without leaking private data, and the API never imports
the execution host (the runner must stay a separate process with its own trust
boundary).
"""
import ast
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


class _Records(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_every_response_carries_a_correlation_id(client):
    for path in ("/health", "/api/definitely-missing"):
        response = client.get(path)
        assert response.headers.get("X-Request-ID"), path
        assert len(response.headers["X-Request-ID"]) == 36


def test_the_log_line_repeats_the_id_and_never_the_payload(client):
    records = _Records()
    logger = logging.getLogger("mentor.request")
    logger.addHandler(records)
    logger.setLevel(logging.INFO)
    try:
        response = client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    finally:
        logger.removeHandler(records)
    request_id = response.headers["X-Request-ID"]
    assert any(request_id in message and "route=/auth/login" in message for message in records.messages), records.messages
    joined = " ".join(records.messages)
    assert "wrong-password" not in joined, "пароль не должен попадать в лог"
    assert "nobody@example.com" not in joined.split("route=")[0], "логин не пишется в строку запроса"


def test_api_never_imports_the_execution_host():
    offenders = []
    for path in APP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name == "runner_worker" or name.startswith("runner_worker."):
                    offenders.append(f"{path.relative_to(APP_ROOT.parent)}:{node.lineno} imports {name}")
    assert offenders == [], offenders


def test_runner_never_imports_the_application():
    runner_root = APP_ROOT.parents[1] / "runner" / "runner_worker"
    offenders = []
    for path in runner_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name == "app" or name.startswith("app."):
                    offenders.append(f"{path.name}:{node.lineno} imports {name}")
    assert offenders == [], offenders
