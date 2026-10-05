from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import ExerciseHint, ExerciseVersion, HintReveal, LessonCompletion, LessonSession, User
from app.db.session import get_db
from app.exercise_hints import _persisted_idempotency_key, _seed_exercise
from app.main import app
from app.learning_content import EXERCISE_HINT_LADDERS, LESSONS
from content_helpers import enable_choice_feedback
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
    assert response.json()["path"]["next_lesson_id"] == "data-types-v1"
    conditions = next(
        row for row in response.json()["path"]["lessons"]
        if row["id"] == "conditions-v1"
    )
    assert conditions["status"] == "locked"
    stamp = response.json()["path"]["lessons"][0]["completed_at"]
    assert complete(client).status_code == 409
    assert client.get("/learning/lessons/variables-v1").status_code == 200
    assert complete(client).json()["path"]["lessons"][0]["completed_at"] == stamp
    assert client.get("/learning/lessons/variables-v1").status_code == 200
    assert complete(client, answer="4").json()["path"]["completed"] == 1
    assert client.get("/learning/lessons/conditions-v1").status_code == 409
    assert complete(client, lesson="conditions-v1", answer="adult").status_code == 409
    assert client.get("/learning/next").json()["id"] == "data-types-v1"
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    assert client.post("/auth/login", json={"email": "learning@example.com", "password": "safe-password"}).status_code == 200
    assert client.get("/learning/path").json()["completed"] == 1
    assert client.get("/learning/lessons/variables-v1").status_code == 200
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(func.count()).select_from(LessonCompletion)) == 1
        assert db.scalar(select(LessonCompletion)).evidence_type == "authored_quiz_correct"


def test_pending_exact_version_flow_can_finish_after_prerequisite_gate_closes(client):
    register(client, "pending-locked-flow@example.com")
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        version = _seed_exercise(db, "conditions-v1")
        db.add(
            LessonSession(
                user_id=user.id,
                lesson_id="conditions-v1",
                exercise_version_id=version.id,
            )
        )
        db.commit()

    shown = client.get("/learning/lessons/conditions-v1")
    assert shown.status_code == 200
    assert shown.json()["id"] == "conditions-v1"
    completed = client.post(
        "/learning/lessons/conditions-v1/complete",
        headers={"X-CSRF-Token": csrf(client)},
        json={"answer": "adult"},
    )
    assert completed.status_code == 200
    assert completed.json()["correct"] is True
    condition = next(
        lesson for lesson in completed.json()["path"]["lessons"]
        if lesson["id"] == "conditions-v1"
    )
    assert condition["status"] == "completed"
    assert completed.json()["path"]["next_lesson_id"] == "variables-v1"


def test_lesson_api_uses_immutable_snapshot_for_display_and_grading(client):
    register(client, "lesson-snapshot@example.com")
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        _seed_exercise(db, "variables-v1")
        db.commit()
    original = client.get("/learning/lessons/variables-v1").json()
    assert "answer" not in original

    authored = next(item for item in LESSONS if item["id"] == "variables-v1")
    original_values = {key: authored[key] for key in ("title", "minutes", "body", "answer")}
    authored.update(
        title="MUTATED authored title",
        minutes=99,
        body="MUTATED authored body",
        answer="4",
    )
    try:
        lesson = client.get("/learning/lessons/variables-v1")
        path = client.get("/learning/path")
        completion = complete(client)
        assert lesson.status_code == path.status_code == completion.status_code == 200
        assert lesson.json()["title"] == original["title"]
        assert lesson.json()["minutes"] == original["minutes"]
        assert lesson.json()["body"] == original["body"]
        summary = next(item for item in path.json()["lessons"] if item["id"] == "variables-v1")
        assert summary["title"] == original["title"]
        assert summary["minutes"] == original["minutes"]
        assert completion.json()["correct"] is True
    finally:
        authored.update(original_values)


def test_lesson_get_post_and_hint_bind_to_exact_version_after_publication(client, monkeypatch):
    register(client, "lesson-binding@example.com")
    onboard(client)
    shown = client.get("/learning/next").json()
    assert shown["id"] == "variables-v1"
    with next(app.dependency_overrides[get_db]()) as db:
        original_version = db.scalar(select(ExerciseVersion).where(
            ExerciseVersion.exercise_id == "variables-v1",
        ))
        original_id = original_version.id
        old_hint = original_version.content_snapshot["hints"][0]["text"]

    original_number = EXERCISE_HINT_LADDERS["variables-v1"]["version"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original_number + 1)
    enable_choice_feedback(monkeypatch, "variables-v1", prefix="published")
    try:
        # Publish a genuinely different answer and hint under the new version.
        authored = next(item for item in LESSONS if item["id"] == "variables-v1")
        original_answer = authored["answer"]
        authored["answer"] = "4"
        original_ladder = EXERCISE_HINT_LADDERS["variables-v1"]["hints"]
        EXERCISE_HINT_LADDERS["variables-v1"]["hints"] = tuple(
            (level, kind, "NEW hint" if level == 1 else text)
            for level, kind, text in original_ladder
        )
        try:
            with next(app.dependency_overrides[get_db]()) as db:
                _seed_exercise(db, "variables-v1")
                db.commit()
            again = client.get("/learning/lessons/variables-v1").json()
            assert again == shown
            hint = client.post(
                "/learning/exercises/variables-v1/hints",
                headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "bound-hint"},
                json={"level": 1},
            )
            assert hint.status_code == 200
            assert hint.json()["text"] == old_hint
            assert complete(client, answer="4").json()["correct"] is False
            result = complete(client, answer="6")
            assert result.status_code == 200 and result.json()["correct"] is True
            assert "exercise_version_id" not in result.text
            with next(app.dependency_overrides[get_db]()) as db:
                completion = db.scalar(select(LessonCompletion))
                session = db.scalar(select(LessonSession))
                reveal = db.scalar(select(HintReveal))
                assert completion.exercise_version_id == session.exercise_version_id == reveal.exercise_version_id == original_id
                assert session.consumed_at is not None
                assert db.get(ExerciseVersion, completion.exercise_version_id).content_snapshot["lesson"]["answer"] == "6"
            assert complete(client, answer="6").status_code == 409
        finally:
            authored["answer"] = original_answer
            EXERCISE_HINT_LADDERS["variables-v1"]["hints"] = original_ladder
    finally:
        monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original_number)


def test_direct_lesson_post_without_get_still_binds_current_version(client):
    register(client, "direct-lesson-post@example.com")
    onboard(client)
    result = complete(client)
    assert result.status_code == 200
    assert result.json()["correct"] is True
    with next(app.dependency_overrides[get_db]()) as db:
        completion = db.scalar(select(LessonCompletion))
        session = db.scalar(select(LessonSession))
        assert completion.exercise_version_id == session.exercise_version_id
        assert session.consumed_at is not None


def test_lesson_invalid_pending_binding_returns_409(client):
    register(client, "invalid-lesson-binding@example.com")
    onboard(client)
    assert client.get("/learning/lessons/variables-v1").status_code == 200
    with next(app.dependency_overrides[get_db]()) as db:
        session = db.scalar(select(LessonSession))
        session.exercise_version_id = _seed_exercise(db, "conditions-v1").id
        db.commit()
    assert complete(client).status_code == 409
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(LessonCompletion)) is None


def test_lesson_api_rejects_missing_snapshot(client):
    register(client, "missing-snapshot@example.com")
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        version = _seed_exercise(db, "variables-v1")
        version.content_snapshot = None
        db.commit()

    assert client.get("/learning/lessons/variables-v1").status_code == 409
    assert client.get("/learning/path").status_code == 409
    assert complete(client).status_code == 409

    with next(app.dependency_overrides[get_db]()) as db:
        version = db.scalar(select(ExerciseVersion).where(ExerciseVersion.exercise_id == "variables-v1"))
        version.content_snapshot = {}
        db.commit()

    assert client.get("/learning/lessons/variables-v1").status_code == 409


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


def test_hint_ladder_reveals_one_next_level_and_is_append_only(client):
    register(client)
    onboard(client)
    headers = {"X-CSRF-Token": csrf(client), "Idempotency-Key": "variables-hint-1"}

    first = client.post("/learning/exercises/variables-v1/hints", headers=headers, json={"level": 1})
    assert first.status_code == 200
    response = client.post(
        "/learning/exercises/variables-v1/hints",
        headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "variables-hint-2"},
        json={"level": 2},
    )
    assert response.status_code == 200
    assert set(response.json()) == {"level", "kind", "text"}
    assert response.json()["level"] == 2
    assert client.post(
        "/learning/exercises/variables-v1/hints",
        headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "variables-hint-repeat"},
        json={"level": 2},
    ).status_code == 409
    assert client.post(
        "/learning/exercises/variables-v1/hints",
        headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "variables-hint-skip"},
        json={"level": 4},
    ).status_code == 409
    assert client.post(
        "/learning/exercises/variables-v1/hints",
        headers={"Idempotency-Key": "variables-hint-no-csrf"},
        json={"level": 3},
    ).status_code == 403

    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(func.count()).select_from(ExerciseVersion)) == len(LESSONS)
        assert db.scalar(select(func.count()).select_from(ExerciseHint)) == 5
        assert db.scalar(select(func.count()).select_from(HintReveal)) == 2


def test_same_idempotency_key_replays_response_and_is_scoped_to_version(client, monkeypatch):
    register(client)
    onboard(client)
    headers = {"X-CSRF-Token": csrf(client), "Idempotency-Key": "retry-key"}

    first = client.post("/learning/exercises/variables-v1/hints", headers=headers, json={"level": 1})
    replay = client.post("/learning/exercises/variables-v1/hints", headers=headers, json={"level": 1})
    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert client.post(
        "/learning/exercises/variables-v1/hints",
        headers=headers,
        json={"level": 2},
    ).status_code == 409

    original = EXERCISE_HINT_LADDERS["variables-v1"]["version"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original + 1)
    enable_choice_feedback(monkeypatch, "variables-v1", prefix="retry")
    try:
        second_version = client.post(
            "/learning/exercises/variables-v1/hints",
            headers=headers,
            json={"level": 1},
        )
        assert second_version.status_code == 200
    finally:
        monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original)


def test_hint_response_uses_immutable_version_snapshot(client, monkeypatch):
    register(client, "immutable-content@example.com")
    onboard(client)
    headers = {"X-CSRF-Token": csrf(client), "Idempotency-Key": "immutable-hint-1"}
    first = client.post("/learning/exercises/variables-v1/hints", headers=headers, json={"level": 1})
    assert first.status_code == 200

    with next(app.dependency_overrides[get_db]()) as db:
        version = _seed_exercise(db, "variables-v1")
        original_snapshot = version.content_snapshot
        original_level_two = original_snapshot["hints"][1]["text"]

    original_hints = EXERCISE_HINT_LADDERS["variables-v1"]["hints"]
    changed_hints = tuple(
        (level, kind, "CHANGED authored text")
        if level == 2
        else (level, kind, text)
        for level, kind, text in original_hints
    )
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "hints", changed_hints)
    try:
        response = client.post(
            "/learning/exercises/variables-v1/hints",
            headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "immutable-hint-2"},
            json={"level": 2},
        )
        assert response.status_code == 200
        assert response.json()["text"] == original_level_two
        assert "answer" not in response.text
        assert "exercise_version_id" not in response.text
        with next(app.dependency_overrides[get_db]()) as db:
            version = _seed_exercise(db, "variables-v1")
            assert version.content_snapshot == original_snapshot
    finally:
        monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "hints", original_hints)

    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(func.count()).select_from(HintReveal)) == 2
        assert len(db.scalars(select(HintReveal).where(HintReveal.user_id.is_not(None))).all()) == 2


def test_legacy_raw_key_replays_only_for_its_version_and_level(client, monkeypatch):
    register(client, "legacy-key@example.com")
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User))
        version = _seed_exercise(db, "variables-v1")
        version_id = version.id
        hint = db.scalar(
            select(ExerciseHint).where(
                ExerciseHint.exercise_version_id == version.id,
                ExerciseHint.level == 1,
            )
        )
        db.add(
            HintReveal(
                user_id=user.id,
                exercise_version_id=version.id,
                hint_id=hint.id,
                level=1,
                idempotency_key="legacy-raw-key",
            )
        )
        db.commit()

    replay = client.post(
        "/learning/exercises/variables-v1/hints",
        headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "legacy-raw-key"},
        json={"level": 1},
    )
    assert replay.status_code == 200
    assert client.post(
        "/learning/exercises/variables-v1/hints",
        headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "legacy-raw-key"},
        json={"level": 2},
    ).status_code == 409

    original = EXERCISE_HINT_LADDERS["variables-v1"]["version"]
    monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original + 1)
    enable_choice_feedback(monkeypatch, "variables-v1", prefix="legacy-replay")
    try:
        second_version = client.post(
            "/learning/exercises/variables-v1/hints",
            headers={"X-CSRF-Token": csrf(client), "Idempotency-Key": "legacy-raw-key"},
            json={"level": 1},
        )
        assert second_version.status_code == 200
    finally:
        monkeypatch.setitem(EXERCISE_HINT_LADDERS["variables-v1"], "version", original)

    with next(app.dependency_overrides[get_db]()) as db:
        version_reveals = db.scalars(
            select(HintReveal).where(HintReveal.exercise_version_id == version_id)
        ).all()
        assert len(version_reveals) == 1
        assert version_reveals[0].idempotency_key == "legacy-raw-key"
        second_version_reveal = db.scalar(
            select(HintReveal).where(HintReveal.exercise_version_id != version_id)
        )
        assert second_version_reveal.idempotency_key == _persisted_idempotency_key(
            second_version_reveal.exercise_version_id,
            "legacy-raw-key",
        )


def test_seed_re_reads_after_primary_unique_conflict(client, monkeypatch):
    register(client)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        seeded = _seed_exercise(db, "variables-v1")
        original_scalar = db.scalar
        calls = 0

        def return_missing_once(statement, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return None
            return original_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(db, "scalar", return_missing_once)
        recovered = _seed_exercise(db, "variables-v1")
        assert recovered.id == seeded.id


def test_seed_handles_expected_primary_unique_integrity_error(client, monkeypatch):
    register(client)
    onboard(client)
    with next(app.dependency_overrides[get_db]()) as db:
        seeded = _seed_exercise(db, "variables-v1")
        original_flush = db.flush
        failed = False

        def fail_once(*args, **kwargs):
            nonlocal failed
            if not failed:
                failed = True
                raise IntegrityError(
                    "INSERT",
                    {},
                    Exception("UNIQUE constraint failed: exercise_versions.exercise_id, exercise_versions.version"),
                )
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(db, "flush", fail_once)
        recovered = _seed_exercise(db, "variables-v1")
        assert recovered.id == seeded.id
