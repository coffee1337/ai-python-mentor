"""Private project source and persistent vacancy-to-lesson continuity."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import event, func, select

from app.db.models import LessonCompletion, SkillEvidence, User
from app.db.product_models import ProjectSubmission, VacancyAnalysis, VacancyTarget
from app.db.session import get_db
from app.learning_content import LESSONS
from app.main import app
from app.projects import PROJECT_TEMPLATES
from test_auth import client, csrf


def setup_account(client, email="continuity@example.com"):
    assert client.post("/auth/register", json={"email": email, "password": "safe-password"}).status_code == 201
    assert client.post("/onboarding", headers=headers(client), json={
        "experience_level": "beginner", "target_role": "Python Backend", "weekly_minutes": 180,
    }).status_code == 200


def headers(client):
    return {"X-CSRF-Token": csrf(client)}


def project(client, index=0):
    response = client.post("/projects", headers=headers(client), json={"template_id": PROJECT_TEMPLATES[index]["id"]})
    assert response.status_code == 201
    return response.json()


def submit(client, selected, artifact, key):
    milestone = selected["milestones"][0]
    response = client.post(f"/projects/{selected['id']}/milestones/{milestone['id']}/submissions", headers=headers(client), json={
        "artifact_text": artifact, "repository_url": "https://example.com/private-repo", "idempotency_key": key,
    })
    assert response.status_code == 201
    return response.json()


def test_owner_source_is_exact_read_only_and_history_portfolio_are_redacted(client):
    setup_account(client)
    selected = project(client)
    artifact = "Черновик: café, 🐍 и русский текст.\nНеизменяемый материал для дальнейшей правки."
    first = submit(client, selected, artifact, "initial-private-material")
    url = f"/projects/{selected['id']}/submissions/{first['id']}"
    with next(app.dependency_overrides[get_db]()) as db:
        before = (db.scalar(select(func.count()).select_from(ProjectSubmission)),
                  db.scalar(select(func.count()).select_from(SkillEvidence)))

    for _ in range(2):
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json() == {**first, "artifact_text": artifact}
        assert not {"idempotency_key", "payload_hash", "project_id", "user_id"} & response.json().keys()
    for response in [client.get(f"/projects/{selected['id']}"), client.get("/projects")]:
        assert response.status_code == 200
        assert "artifact_text" not in response.text
        assert artifact not in response.text
        assert "idempotency_key" not in response.text and "payload_hash" not in response.text
    detail = client.get(f"/projects/{selected['id']}").json()
    assert detail["submissions"] == [first]
    with next(app.dependency_overrides[get_db]()) as db:
        after = (db.scalar(select(func.count()).select_from(ProjectSubmission)),
                 db.scalar(select(func.count()).select_from(SkillEvidence)))
        assert after == before

    revised = "\n".join(f"## {section}\nПодробное описание решений и ограничений." for section in selected["milestones"][0]["required_sections"])
    second = submit(client, selected, revised, "revised-private-material")
    assert first["validation"]["status"] == "needs_revision"
    assert second["validation"]["status"] == "artifact_received"
    assert client.get(url).json() == {**first, "artifact_text": artifact}
    assert client.get(f"/projects/{selected['id']}/submissions/{second['id']}").json()["artifact_text"] == revised
    detail = client.get(f"/projects/{selected['id']}").json()
    assert detail["milestones"][0]["latest_submission"]["id"] == second["id"]
    assert {row["id"] for row in detail["submissions"]} == {first["id"], second["id"]}

    publication = client.patch(f"/projects/{selected['id']}/portfolio", headers=headers(client), json={
        "published": True, "title": "Учебный CLI", "summary": "Опубликованное описание учебной работы.", "repository_url": None,
    }).json()
    public = client.get(publication["public_path"]).json()
    assert set(public) == {"title", "summary", "repository_url", "verification", "updated_at"}
    assert "artifact_text" not in str(public) and artifact not in str(public) and revised not in str(public)
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(func.count()).select_from(SkillEvidence)) == before[1]


def test_project_source_rejects_foreign_project_and_mismatched_submission(client):
    setup_account(client)
    selected = project(client)
    other = project(client, 1)
    saved = submit(client, selected, "Исходный закрытый материал этапа проекта владельца.", "owned-source-material")
    assert client.get(f"/projects/{other['id']}/submissions/{saved['id']}").status_code == 404
    assert client.get(f"/projects/{selected['id']}/submissions/{uuid4()}").status_code == 404
    client.post("/auth/logout", headers=headers(client))
    setup_account(client, "foreign-continuity@example.com")
    own = project(client)
    assert client.get(f"/projects/{selected['id']}/submissions/{saved['id']}").status_code == 404
    assert client.get(f"/projects/{own['id']}/submissions/{saved['id']}").status_code == 404


def test_project_metadata_is_bounded_and_never_contains_source(client):
    setup_account(client)
    selected = project(client)
    with next(app.dependency_overrides[get_db]()) as db:
        old_completed = ProjectSubmission(
            project_id=UUID(selected["id"]), milestone_id=selected["milestones"][1]["id"],
            idempotency_key="older-completed-milestone", payload_hash="b" * 64,
            artifact_text="OLDER PRIVATE COMPLETED MATERIAL", repository_url=None,
            validation={"status": "artifact_received", "missing_sections": [], "execution_status": "not_executed", "mastery_credit": False, "message": "Материал принят."},
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        db.add(old_completed)
        db.flush()
        completed_id = str(old_completed.id)
        for index in range(105):
            db.add(ProjectSubmission(project_id=UUID(selected["id"]), milestone_id=selected["milestones"][0]["id"],
                                     idempotency_key=f"bounded-{index}", payload_hash="a" * 64,
                                     artifact_text="PRIVATE SOURCE SHOULD STAY PRIVATE", repository_url=None,
                                     validation={"status": "needs_revision", "missing_sections": [], "execution_status": "not_executed", "mastery_credit": False, "message": "Добавьте разделы."},
                                     created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=index)))
        db.commit()
    response = client.get(f"/projects/{selected['id']}")
    assert len(response.json()["submissions"]) == 100
    assert "PRIVATE SOURCE" not in response.text and "artifact_text" not in response.text
    assert response.json()["milestones"][1]["latest_submission"]["id"] == completed_id
    assert response.json()["milestones"][1]["latest_submission"]["validation"]["status"] == "artifact_received"
    history = client.get("/projects").json()[0]
    assert len(history["submissions"]) == 100
    assert history["milestones"][1]["latest_submission"]["id"] == completed_id
    assert client.get(f"/projects/{selected['id']}/submissions/{completed_id}").json()["artifact_text"] == "OLDER PRIVATE COMPLETED MATERIAL"


def vacancy(client):
    response = client.post("/vacancies", headers=headers(client), json={
        "title": "Python Backend", "text": "Требования: FastAPI и PostgreSQL. Желательно pytest.",
    })
    assert response.status_code == 201
    return response.json()


def test_selected_vacancy_survives_reload_and_recent_history_bound(client):
    setup_account(client)
    assert client.get("/vacancies/current").json() == {"selected": False}
    selected = vacancy(client)
    assert client.post(f"/vacancies/{selected['id']}/target", headers=headers(client)).json()["selected"] is True
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User).where(User.email == "continuity@example.com"))
        old = db.get(VacancyAnalysis, UUID(selected["id"]))
        old.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for index in range(55):
            db.add(VacancyAnalysis(user_id=user.id, title=f"Более новая вакансия {index}", source_text="Приватный текст вакансии",
                                  source_url=None, analyzer_version="authored-keywords-v1", requirements=[],
                                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=index)))
        db.commit()
    for _ in range(2):
        current = client.get("/vacancies/current")
        assert current.status_code == 200 and current.json()["id"] == selected["id"]
        assert current.json()["selected"] is True
        history = client.get("/vacancies").json()
        assert len(history) == 51
        assert [row["id"] for row in history if row["selected"]] == [selected["id"]]
        assert all("text" not in row and "source_text" not in row for row in history)
    assert client.delete(f"/vacancies/{selected['id']}", headers=headers(client)).status_code == 204
    assert client.get("/vacancies/current").json() == {"selected": False}


def test_vacancy_roadmap_links_follow_readiness_and_active_publication(client):
    setup_account(client)
    selected = vacancy(client)
    active = {lesson["skill_id"]: lesson for lesson in LESSONS}
    basic = next(row for row in selected["roadmap"] if row["skill_id"] == "python.variables")
    assert basic["lesson_id"] == active["python.variables"]["id"]
    assert basic["lesson_status"] == "available"
    assert client.get(f"/learning/lessons/{basic['lesson_id']}").status_code == 200
    locked = next(row for row in selected["roadmap"] if row["skill_id"] == "backend.fastapi_basics")
    assert locked["lesson_status"] == "locked"
    assert client.get(f"/learning/lessons/{locked['lesson_id']}").status_code == 409
    assert locked["prerequisite_lesson_id"] == basic["lesson_id"]
    assert locked["prerequisite_lesson_title"] == basic["lesson_title"]
    assert client.get(f"/learning/lessons/{locked['prerequisite_lesson_id']}").status_code == 200
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User).where(User.email == "continuity@example.com"))
        db.add(LessonCompletion(user_id=user.id, lesson_id="variables-v1", answer="legacy stored answer"))
        db.commit()
    refreshed = client.get(f"/vacancies/{selected['id']}").json()
    completed = next(row for row in refreshed["roadmap"] if row["skill_id"] == "python.variables")
    assert completed["lesson_id"] == active["python.variables"]["id"]
    assert completed["lesson_status"] == "completed"
    assert client.get(f"/learning/lessons/{completed['lesson_id']}").status_code == 200
    first_unmet = next(row for row in refreshed["roadmap"] if row["skill_id"] == "backend.fastapi_basics")
    assert first_unmet["prerequisite_lesson_id"] != basic["lesson_id"]
    assert client.get(f"/learning/lessons/{first_unmet['prerequisite_lesson_id']}").status_code == 200


def test_foreign_vacancy_target_never_leaks_detail_or_selection(client):
    setup_account(client)
    foreign = vacancy(client)
    client.post("/auth/logout", headers=headers(client))
    setup_account(client, "other-target@example.com")
    own = vacancy(client)
    assert client.get(f"/vacancies/{foreign['id']}").status_code == 404
    assert client.post(f"/vacancies/{foreign['id']}/target", headers=headers(client)).status_code == 404
    # Even an inconsistent legacy target pointer must not disclose another owner.
    with next(app.dependency_overrides[get_db]()) as db:
        user = db.scalar(select(User).where(User.email == "other-target@example.com"))
        db.add(VacancyTarget(user_id=user.id, vacancy_id=UUID(foreign["id"])))
        db.commit()
    assert client.get("/vacancies/current").json() == {"selected": False}
    history = client.get("/vacancies").json()
    assert [row["id"] for row in history] == [own["id"]]
    assert all(row["selected"] is False for row in history)


def test_vacancy_reads_do_not_publish_seed_or_create_learning_records(client):
    setup_account(client)
    selected = vacancy(client)
    assert client.post(f"/vacancies/{selected['id']}/target", headers=headers(client)).status_code == 200
    with next(app.dependency_overrides[get_db]()) as db:
        engine = db.get_bind()
    writes = []

    def collect_writes(_connection, _cursor, statement, _parameters, _context, _many):
        normalized = statement.strip().lower()
        if normalized.startswith(("insert ", "update ", "delete ")) and not normalized.startswith("update auth_sessions "):
            writes.append(normalized.split()[0:3])

    event.listen(engine, "before_cursor_execute", collect_writes)
    try:
        for path in ["/vacancies", "/vacancies/current", f"/vacancies/{selected['id']}"]:
            assert client.get(path).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", collect_writes)
    assert writes == []
