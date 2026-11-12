"""Admin content surface: read-only, complete, and closed to non-admins.

The numbers here are the same ones the CI content audit enforces, so an operator
and the test suite cannot disagree about what the course contains.
"""
import pytest
from sqlalchemy import select
from test_auth import client, csrf
from test_learning import onboard, register

from app.content_audit import report
from app.db.models import User
from app.db.session import get_db
from app.main import app


def make_admin(monkeypatch) -> str:
    with next(app.dependency_overrides[get_db]()) as db:
        user_id = db.scalar(select(User.id))
    monkeypatch.setenv("ADMIN_USER_IDS", str(user_id))
    return str(user_id)


def test_overview_matches_the_audit(client, monkeypatch):
    register(client)
    onboard(client)
    make_admin(monkeypatch)
    response = client.get("/admin/content/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    expected = report()
    assert body["lessons"] == 90 and body["exercises"] == 90 and body["cases"] == 288
    assert body["healthy"] is True, body["lesson_issues"][:5] + body["exercise_issues"][:5]
    assert body["knowledge_chunks"] == expected["knowledge_chunks"] > 0


def test_lessons_listing_supports_filters(client, monkeypatch):
    register(client)
    make_admin(monkeypatch)
    everything = client.get("/admin/content/lessons?limit=200").json()
    assert everything["total"] == 90
    assert all({"id", "title", "skill_id", "phase", "practice", "has_exercise"} <= set(item) for item in everything["lessons"])

    filtered = client.get("/admin/content/lessons?query=переменн").json()
    assert 0 < filtered["returned"] <= everything["returned"]
    assert all("переменн" in (item["title"] or "").casefold() or "variables" in item["id"] for item in filtered["lessons"])

    coding = [item for item in everything["lessons"] if item["has_exercise"]]
    reading = [item for item in everything["lessons"] if item["practice"] == "guided_reading"]
    # Three republished lessons are authored as reading; they must not demand coding.
    assert {item["id"] for item in reading} == {"variables-v2", "data-types-v2", "conditions-v2"}
    assert len(coding) == 90 - len(reading) == 87


def test_lesson_detail_shows_checks_and_exercise(client, monkeypatch):
    register(client)
    make_admin(monkeypatch)
    lesson = client.get("/admin/content/lessons/variables-v2")
    assert lesson.status_code == 200, lesson.text
    body = lesson.json()
    assert body["id"] == "variables-v2" and body["body_chars"] > 200
    assert body["checks"], "у урока есть проверка знаний"
    assert client.get("/admin/content/lessons/does-not-exist").status_code == 404


def test_exercises_carry_hidden_cases(client, monkeypatch):
    register(client)
    make_admin(monkeypatch)
    body = client.get("/admin/content/exercises").json()
    assert body["total"] == 90
    assert all(item["hidden"] >= 1 for item in body["exercises"]), "у каждого задания есть скрытые кейсы"


def test_content_admin_is_closed_to_learners(client):
    register(client)
    for path in ("/admin/content/overview", "/admin/content/lessons", "/admin/content/exercises"):
        assert client.get(path).status_code == 403, path
