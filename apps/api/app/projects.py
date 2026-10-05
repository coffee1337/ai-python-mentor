"""Versioned project milestones and opt-in, deliberately redacted portfolio."""
import hashlib
import json
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import csrf_protected, current_auth
from app.db.models import AuthSession, User
from app.db.product_models import LearnerProject, PortfolioEntry, ProjectSubmission
from app.db.session import get_db
from app.learning import require_onboarding
from app.vacancies import public_source_url

router = APIRouter(tags=["projects"])


def _template(slug, title, skills, requirements, milestones):
    return {"id": f"{slug}-v1", "version": 1, "title": title, "skill_ids": skills,
            "requirements": requirements, "milestones": [
                {"id": f"{slug}-{index + 1}-v1", "title": item[0], "required_sections": item[1],
                 "instructions": item[2]} for index, item in enumerate(milestones)]}


PROJECT_TEMPLATES = [
    _template("expense-cli", "CLI учёта расходов", ["python.functions", "python.dictionaries", "python.exceptions"],
              ["Добавление расхода с суммой и категорией", "Отчёт по категориям", "JSON-хранилище и обработка ошибок"], [
                  ("Требования и интерфейс", ["Требования", "Команды"], "Опишите add/list/report и поведение неверного ввода."),
                  ("Хранение и реализация", ["Формат данных", "Реализация"], "Приведите JSON-схему и ключевые функции; избегайте реальных финансовых данных."),
                  ("Тесты", ["Тесты", "Запуск"], "Покажите тесты пустого списка, отрицательной суммы и повреждённого файла.")]),
    _template("http-client", "HTTP-клиент", ["backend.http_basics", "backend.error_handling"],
              ["Timeout", "Обработка статусов и невалидного JSON", "Mock HTTP в тестах"], [
                  ("Контракт", ["Запрос", "Ошибки"], "Опишите URL-конфигурацию, формат результата, таймауты и статусы."),
                  ("Клиент и тесты", ["Реализация", "Тесты"], "Приведите код клиента и тесты timeout/500/invalid JSON без внешней сети.")]),
    _template("crud-api", "CRUD API задач", ["backend.fastapi_basics", "backend.request_validation"],
              ["Создание, чтение, изменение, удаление задач", "422 для неверного ввода", "404 для отсутствующего ресурса"], [
                  ("API-контракт", ["Endpoints", "Валидация"], "Опишите методы, пути, схемы и коды ответов."),
                  ("Реализация", ["Реализация", "Тесты"], "Приведите маршруты и тесты каждого метода и ошибки 404/422.")]),
    _template("auth-api", "Аутентификация и доступ", ["backend.authentication", "backend.authorization", "backend.csrf"],
              ["Хеши паролей", "Отзыв сессий", "Защита чужих данных", "CSRF для cookie-сессий"], [
                  ("Модель угроз", ["Угрозы", "Сессии"], "Разберите кражу сессии, CSRF, подбор и доступ к чужому ресурсу."),
                  ("Реализация и проверки", ["Реализация", "Тесты"], "Покажите негативные тесты доступа; не включайте пароли и токены.")]),
    _template("postgres-api", "API с PostgreSQL", ["backend.postgresql", "backend.transactions", "backend.migrations"],
              ["Миграции", "Транзакции", "Ограничения БД", "Проверки на PostgreSQL"], [
                  ("Схема", ["Таблицы", "Ограничения"], "Опишите ключи, уникальность, индексы и границы транзакций."),
                  ("Миграции и тесты", ["Миграции", "Тесты"], "Покажите upgrade/downgrade и проверку rollback на PostgreSQL.")]),
    _template("redis-cache", "Кеширование", ["backend.caching", "backend.redis_basics"],
              ["TTL", "Инвалидация", "Работа при недоступном кеше"], [
                  ("Политика кеша", ["Ключи", "Инвалидация"], "Опишите tenant-scoped ключи, TTL и сброс после записи."),
                  ("Реализация и деградация", ["Реализация", "Тесты"], "Покажите cache miss, stale data и сбой Redis.")]),
    _template("background-jobs", "Фоновые задания", ["backend.background_tasks", "backend.error_handling"],
              ["Долговечная очередь", "Идемпотентность", "Ограниченные повторы", "Статус задания"], [
                  ("Состояния задания", ["Состояния", "Идемпотентность"], "Опишите pending/running/success/failure и повтор после падения worker."),
                  ("Worker и тесты", ["Реализация", "Тесты"], "Покажите deduplication, retry limit и восстановление потерянной аренды.")]),
    _template("docker-service", "Docker-развёртывание", ["backend.docker_basics", "backend.configuration"],
              ["Non-root", "Health/readiness", "Конфигурация без секретов в образе", "Backup/restore"], [
                  ("Конфигурация", ["Dockerfile", "Конфигурация"], "Приведите сборку и compose без настоящих секретов."),
                  ("Эксплуатация", ["Health", "Восстановление"], "Опишите готовность, обновление миграций и тест восстановления backup.")]),
    _template("final-backend", "Итоговый Python Backend", ["backend.api_design", "backend.security_basics", "backend.observability"],
              ["API с авторизацией", "PostgreSQL и миграции", "Тесты и CI", "Операционная инструкция"], [
                  ("Проектирование", ["Требования", "Архитектура", "API"], "Опишите границы модулей, угрозы, схемы и ограничения продукта."),
                  ("Реализация", ["Реализация", "Миграции"], "Приведите ключевые решения и процедуры безопасной миграции."),
                  ("Проверка и запуск", ["Тесты", "CI", "Запуск"], "Приложите результаты проверок, ограничения и шаги воспроизводимого запуска.")]),
]
TEMPLATES = {item["id"]: item for item in PROJECT_TEMPLATES}


class StartProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: str = Field(min_length=1, max_length=80)


class MilestoneSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_text: str = Field(min_length=30, max_length=25000)
    repository_url: str | None = Field(default=None, max_length=2048)
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("repository_url")
    @classmethod
    def safe_url(cls, value):
        return public_source_url(value)


class PortfolioPublication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    published: bool
    title: str = Field(min_length=2, max_length=160)
    summary: str = Field(min_length=10, max_length=2000)
    repository_url: str | None = Field(default=None, max_length=2048)

    @field_validator("repository_url")
    @classmethod
    def safe_url(cls, value):
        return public_source_url(value)


def _owned(db, user, project_id):
    project = db.scalar(select(LearnerProject).where(LearnerProject.id == project_id, LearnerProject.user_id == user.id))
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


def _submission_response(row):
    return {"id": str(row.id), "milestone_id": row.milestone_id, "validation": row.validation,
            "repository_url": row.repository_url, "created_at": row.created_at}


def _project_response(db, project):
    submissions = db.scalars(select(ProjectSubmission).where(ProjectSubmission.project_id == project.id).order_by(ProjectSubmission.created_at.desc()).limit(100)).all()
    latest = {}
    for submission in submissions:
        latest.setdefault(submission.milestone_id, _submission_response(submission))
    portfolio = db.scalar(select(PortfolioEntry).where(PortfolioEntry.project_id == project.id))
    return {"id": str(project.id), "template": project.template_snapshot, "milestones": [
        {**item, "latest_submission": latest.get(item["id"])} for item in project.template_snapshot["milestones"]],
        "created_at": project.created_at, "portfolio": None if portfolio is None else {
            "published": portfolio.published, "title": portfolio.title, "summary": portfolio.summary,
            "repository_url": portfolio.repository_url, "public_path": f"/portfolio/{portfolio.public_token}" if portfolio.published else None},
        "notice": "Проверяется комплектность артефакта. Код проекта и тесты не исполняются; это не подтверждение самостоятельного mastery."}


@router.get("/projects/templates")
def templates(auth: tuple[User, AuthSession] = Depends(current_auth)):
    return PROJECT_TEMPLATES


@router.get("/projects")
def history(auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    rows = db.scalars(select(LearnerProject).where(LearnerProject.user_id == auth[0].id).order_by(LearnerProject.created_at.desc()).limit(50))
    return [_project_response(db, row) for row in rows]


@router.post("/projects", status_code=201)
def start(payload: StartProject, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    require_onboarding(auth[0])
    template = TEMPLATES.get(payload.template_id)
    if template is None:
        raise HTTPException(404, "Project template not found")
    existing = db.scalar(select(LearnerProject).where(LearnerProject.user_id == auth[0].id, LearnerProject.template_id == payload.template_id))
    if existing:
        return _project_response(db, existing)
    row = LearnerProject(user_id=auth[0].id, template_id=payload.template_id, template_snapshot=json.loads(json.dumps(template)))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.scalar(select(LearnerProject).where(LearnerProject.user_id == auth[0].id, LearnerProject.template_id == payload.template_id))
        if row is None:
            raise HTTPException(409, "Project could not be started") from None
    return _project_response(db, row)


@router.get("/projects/{project_id}")
def detail(project_id: UUID, auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    return _project_response(db, _owned(db, auth[0], project_id))


@router.post("/projects/{project_id}/milestones/{milestone_id}/submissions", status_code=201)
def submit(project_id: UUID, milestone_id: str, payload: MilestoneSubmission, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    project = _owned(db, auth[0], project_id)
    milestone = next((item for item in project.template_snapshot["milestones"] if item["id"] == milestone_id), None)
    if milestone is None:
        raise HTTPException(404, "Milestone not found")
    digest = hashlib.sha256(json.dumps({"milestone_id": milestone_id, **payload.model_dump(exclude={"idempotency_key"})}, sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(ProjectSubmission).where(ProjectSubmission.project_id == project_id, ProjectSubmission.idempotency_key == payload.idempotency_key))
    if existing:
        if existing.payload_hash != digest:
            raise HTTPException(409, "Idempotency key already used with different content")
        return _submission_response(existing)
    sections = {line.lstrip("# ").rstrip(": ").casefold() for line in payload.artifact_text.splitlines()}
    missing = [section for section in milestone["required_sections"] if section.casefold() not in sections]
    validation = {"status": "needs_revision" if missing else "artifact_received", "missing_sections": missing,
                  "execution_status": "not_executed", "mastery_credit": False,
                  "message": "Добавьте обязательные разделы." if missing else "Артефакт принят. Полнота разделов проверена; корректность кода требует отдельной проверки."}
    row = ProjectSubmission(project_id=project_id, milestone_id=milestone_id, idempotency_key=payload.idempotency_key,
                            payload_hash=digest, artifact_text=payload.artifact_text, repository_url=payload.repository_url, validation=validation)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(ProjectSubmission).where(ProjectSubmission.project_id == project_id, ProjectSubmission.idempotency_key == payload.idempotency_key))
        if existing is None or existing.payload_hash != digest:
            raise HTTPException(409, "Submission already exists with different content") from None
        row = existing
    return _submission_response(row)


@router.patch("/projects/{project_id}/portfolio")
def publish(project_id: UUID, payload: PortfolioPublication, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    project = _owned(db, auth[0], project_id)
    entry = db.scalar(select(PortfolioEntry).where(PortfolioEntry.project_id == project_id))
    if entry is None:
        entry = PortfolioEntry(user_id=auth[0].id, project_id=project_id, public_token=secrets.token_urlsafe(32))
    for name, value in payload.model_dump().items():
        setattr(entry, name, value)
    db.add(entry)
    db.commit()
    return _project_response(db, project)["portfolio"]


@router.get("/portfolio/{public_token}")
def public_portfolio(public_token: str, db: Session = Depends(get_db)):
    if len(public_token) > 64:
        raise HTTPException(404, "Portfolio not found")
    entry = db.scalar(select(PortfolioEntry).where(PortfolioEntry.public_token == public_token, PortfolioEntry.published.is_(True)))
    if entry is None:
        raise HTTPException(404, "Portfolio not found")
    # Only fields the learner expressly selected for publication. No account
    # identity, private source, grading material, or claim of verified skills.
    return {"title": entry.title, "summary": entry.summary, "repository_url": entry.repository_url,
            "verification": "learner_published", "updated_at": entry.updated_at}


@router.delete("/projects/{project_id}", status_code=204)
def delete(project_id: UUID, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    project = _owned(db, auth[0], project_id)
    for row in db.scalars(select(PortfolioEntry).where(PortfolioEntry.project_id == project_id)):
        db.delete(row)
    for row in db.scalars(select(ProjectSubmission).where(ProjectSubmission.project_id == project_id)):
        db.delete(row)
    db.flush()
    db.delete(project)
    db.commit()
