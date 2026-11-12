"""Feature flags and product analytics: determinism, allow-list, admin-only reads.

The tests pin the properties that matter operationally: a user never flips between
requests, an override beats the percentage and is audited, event props never carry
free text, and the funnel is computed from stored facts only.
"""
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_auth import client, csrf
from test_learning import onboard, register

from app import analytics, feature_flags
from app.db.models import FeatureFlagOverride, ProductEvent, User
from app.db.session import get_db
from app.main import app

ADMIN_ENV = "ADMIN_USER_IDS"


def make_admin(monkeypatch) -> str:
    """Promote the account that already exists to administrator."""
    with next(app.dependency_overrides[get_db]()) as db:
        user_id = db.scalar(select(User.id))
    monkeypatch.setenv(ADMIN_ENV, str(user_id))
    return str(user_id)


def test_rollout_is_stable_and_bounded():
    user = uuid4()
    first = [feature_flags.bucket(user, "new_tutor_v2") for _ in range(5)]
    assert len(set(first)) == 1, "один пользователь не должен переключаться между запросами"
    assert 0 <= first[0] < 100
    assert feature_flags.bucket(None, "new_tutor_v2") == 100, "аноним не попадает в rollout"


def test_percentage_and_override(client, monkeypatch):
    register(client)
    admin = make_admin(monkeypatch)
    with next(app.dependency_overrides[get_db]()) as db:
        user_id = db.scalar(select(User.id))
        monkeypatch.setenv("FEATURE_GITHUB_IMPORT_PERCENT", "0")
        assert feature_flags.enabled(db, user_id, "github_import") is False
        feature_flags.override(db, flag="github_import", user_id=user_id, enabled_value=True, actor_id=uuid4() if admin is None else user_id)
        db.commit()
        assert feature_flags.enabled(db, user_id, "github_import") is True, "override важнее процента"
        assert feature_flags.enabled(db, user_id, "unknown_flag") is False


def test_client_sees_only_its_own_flags(client):
    register(client)
    response = client.get("/me/features")
    assert response.status_code == 200
    assert set(response.json()["flags"]) == set(feature_flags.CATALOGUE)


def test_admin_sets_a_flag_and_it_is_audited(client, monkeypatch, caplog):
    register(client)
    admin = make_admin(monkeypatch)
    with next(app.dependency_overrides[get_db]()) as db:
        target = db.scalar(select(User.id))
    caplog.set_level(logging.INFO, logger="growth")
    response = client.post("/admin/features", headers={"X-CSRF-Token": csrf(client)},
                           json={"flag": "new_vacancy_parser", "user_id": str(target), "enabled": True})
    assert response.status_code == 200, response.text
    with next(app.dependency_overrides[get_db]()) as db:
        row = db.get(FeatureFlagOverride, ("new_vacancy_parser", target))
    assert row is not None and row.enabled is True and str(row.updated_by) == str(admin)
    assert any("feature_flag_override" in record.getMessage() for record in caplog.records)


def test_non_admin_cannot_read_or_write_flags(client):
    register(client)
    assert client.get("/admin/features").status_code == 403
    assert client.get("/admin/analytics").status_code == 403


def test_unknown_flag_is_rejected(client, monkeypatch):
    register(client)
    make_admin(monkeypatch)
    with next(app.dependency_overrides[get_db]()) as db:
        target = db.scalar(select(User.id))
    response = client.post("/admin/features", headers={"X-CSRF-Token": csrf(client)},
                           json={"flag": "make_me_admin", "user_id": str(target), "enabled": True})
    assert response.status_code == 422


def test_event_props_are_an_allow_list():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        analytics.emit(db, user_id=None, name="lesson_completed",
                       lesson_id="variables-v2", source_code="print('secret')", email="a@b.c")
        db.commit()
        row = db.scalars(select(ProductEvent)).one()
    assert row.props == {"lesson_id": "variables-v2"}, "лишние поля не сохраняются"
    engine.dispose()


def test_funnel_is_computed_from_events(client, monkeypatch):
    register(client)
    make_admin(monkeypatch)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user_id = db.scalar(select(User.id))
        now = datetime.now(UTC)
        analytics.emit(db, user_id=user_id, name="lesson_completed", lesson_id="variables-v2", source="seed")
        db.add(ProductEvent(id=uuid4(), user_id=user_id, name="session_started", props={},
                            created_at=now - timedelta(days=1)))
        db.commit()
    body = client.get("/admin/analytics?days=30").json()
    assert body["acquisition"]["registered"] >= 1
    assert body["activation"]["completed_onboarding"] >= 1
    assert body["activation"]["rate"] > 0
    assert body["engagement"]["lessons_completed"] >= 1
    assert body["north_star"]["weekly_active_learners"] >= 1
    assert 0 <= body["retention"]["rate"] <= 1
