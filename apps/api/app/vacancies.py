"""Explainable vacancy matching from pasted text, without fetching untrusted URLs."""
import re
from datetime import datetime, timezone
from uuid import UUID
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import csrf_protected, current_auth
from app.db.models import AuthSession, User
from app.db.product_models import VacancyAnalysis, VacancyTarget
from app.db.session import get_db
from app.learning import require_onboarding
from app.skill_graph import SKILLS, seed_skill_graph

router = APIRouter(prefix="/vacancies", tags=["vacancies"])
ANALYZER_VERSION = "authored-keywords-v1"
# Explicit reviewed aliases only; an occurrence is a requirement signal, not a
# claim that the employer requires mastery of every similarly named skill.
ALIASES = {
    "backend.fastapi_basics": ("fastapi",),
    "backend.postgresql": ("postgresql", "postgres"),
    "backend.sql_basics": ("sql",),
    "backend.sqlalchemy_orm": ("sqlalchemy",),
    "backend.redis_basics": ("redis",),
    "backend.docker_basics": ("docker",),
    "backend.git_basics": ("git",),
    "backend.linux_cli": ("linux",),
    "backend.rest": ("rest", "restful"),
    "backend.http_basics": ("http", "https"),
    "backend.async_python": ("asyncio", "асинхрон", "asynchronous"),
    "python.pytest_basics": ("pytest",),
    "backend.ci_basics": ("ci/cd", "continuous integration"),
    "backend.websockets": ("websocket", "websockets"),
    "backend.authentication": ("oauth", "jwt", "аутентификац", "authentication"),
    "backend.caching": ("кеширован", "кэширован", "caching"),
    "backend.security_basics": ("owasp",),
}


def public_source_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Use an HTTPS URL without credentials or a fragment")
    return value


class VacancyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=160)
    text: str = Field(min_length=20, max_length=25000)
    source_url: str | None = Field(default=None, max_length=2048)

    @field_validator("source_url")
    @classmethod
    def url_is_metadata_only(cls, value):
        return public_source_url(value)

    @field_validator("title", "text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Field cannot be blank")
        return value.strip()


def extract_requirements(text: str) -> list[dict]:
    result = []
    seen = set()
    for sentence in re.finditer(r"[^\n.!?]+(?:[.!?]|$)", text):
        evidence = sentence.group().strip()
        lowered = evidence.casefold()
        if not evidence:
            continue
        # Explicitly negated requirements must not become target skills.
        if re.search(r"не\s+(?:требуется|нужен|нужно|обязател)|not\s+required|do\s+not\s+require", lowered):
            continue
        level = "preferred" if re.search(r"желательно|будет плюсом|nice.?to.?have|preferred|bonus", lowered) else (
            "required" if re.search(r"требован|обязател|необходим|must|required|requirement", lowered) else "mentioned"
        )
        for skill_id, aliases in ALIASES.items():
            if skill_id in seen:
                continue
            match = next((re.search(r"(?<!\w)" + re.escape(alias) + (r"(?!\w)" if alias.isascii() else ""), lowered)
                          for alias in aliases if re.search(r"(?<!\w)" + re.escape(alias) + (r"(?!\w)" if alias.isascii() else ""), lowered)), None)
            if match is None:
                continue
            start = sentence.start() + len(sentence.group()) - len(sentence.group().lstrip())
            seen.add(skill_id)
            result.append({"skill_id": skill_id, "level": level, "evidence": evidence,
                           "start": start, "end": start + len(evidence), "match_method": "reviewed_alias"})
    return result


def _owned(db, user, vacancy_id):
    row = db.scalar(select(VacancyAnalysis).where(VacancyAnalysis.id == vacancy_id, VacancyAnalysis.user_id == user.id))
    if row is None:
        raise HTTPException(404, "Vacancy analysis not found")
    return row


def _roadmap(db: Session, user: User, requirements: list[dict]) -> list[dict]:
    from app.prerequisites import MASTERY_READINESS_THRESHOLD
    from app.study_progress import CourseView
    course = CourseView(db, user, datetime.now(timezone.utc))
    rows = course.mastery
    state = course.readiness
    target = {item["skill_id"] for item in requirements}
    closure = target | {required for skill_id in target for required in state.required_skills(skill_id)}
    result = []
    # Only active primary publications are destinations. Completion IDs already
    # include publication replacements in the shared readiness policy.
    lessons = {lesson["skill_id"]: lesson for lesson in course.lessons.values()}
    for skill in SKILLS:
        if skill["id"] not in closure:
            continue
        row = rows.get(skill["id"])
        observed = row is not None and row.evidence_count > 0
        score = (0.45 * row.independent_score + 0.35 * row.knowledge_score + 0.2 * row.practice_score) if observed else None
        lesson = lessons.get(skill["id"])
        lesson_status = None if lesson is None else course.status(lesson)
        prerequisite = None
        if lesson_status == "locked":
            required = state.required_skills(skill["id"])
            prerequisite = next((candidate for candidate in course.lessons.values()
                                 if candidate["skill_id"] in required
                                 and candidate["skill_id"] not in state.completed_primary_skills
                                 and state.mastery.get(candidate["skill_id"], 0) < MASTERY_READINESS_THRESHOLD
                                 and state.is_lesson_ready(candidate)), None)
        result.append({"skill_id": skill["id"], "name": skill["name"],
                       "inferred_prerequisite": skill["id"] not in target,
                       "observation": "observed" if observed else "not_assessed",
                       "mastery_signal": score, "gap": None if score is None else round(max(0, .75 - score), 4),
                       "ready": state.is_skill_ready(skill["id"]),
                       "lesson_id": lesson["id"] if lesson else None,
                       "lesson_title": lesson["title"] if lesson else None,
                       "lesson_status": lesson_status,
                       "prerequisite_lesson_id": prerequisite["id"] if prerequisite else None,
                       "prerequisite_lesson_title": prerequisite["title"] if prerequisite else None})
    return result


def _response(db, user, row):
    target = db.get(VacancyTarget, user.id)
    return {"id": str(row.id), "title": row.title, "text": row.source_text, "source_url": row.source_url,
            "analyzer_version": row.analyzer_version, "requirements": row.requirements,
            "roadmap": _roadmap(db, user, row.requirements), "selected": target is not None and target.vacancy_id == row.id,
            "created_at": row.created_at,
            "notice": "Сопоставлены явные упоминания технологий. Уровень опыта и шанс трудоустройства не оцениваются; проверьте требования вручную."}


@router.post("", status_code=201)
def analyze(payload: VacancyRequest, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    user = auth[0]
    require_onboarding(user)
    seed_skill_graph(db)
    row = VacancyAnalysis(user_id=user.id, title=payload.title, source_text=payload.text,
                          source_url=payload.source_url, analyzer_version=ANALYZER_VERSION,
                          requirements=extract_requirements(payload.text))
    db.add(row)
    db.commit()
    db.refresh(row)
    return _response(db, user, row)


@router.get("")
def history(auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    user = auth[0]
    rows = list(db.scalars(select(VacancyAnalysis).where(VacancyAnalysis.user_id == user.id).order_by(VacancyAnalysis.created_at.desc(), VacancyAnalysis.id.desc()).limit(50)))
    target = db.get(VacancyTarget, user.id)
    selected = None if target is None else db.scalar(select(VacancyAnalysis).where(
        VacancyAnalysis.id == target.vacancy_id, VacancyAnalysis.user_id == user.id,
    ))
    if selected is not None and all(row.id != selected.id for row in rows):
        rows.append(selected)
    return [{"id": str(row.id), "title": row.title, "requirements_count": len(row.requirements),
             "selected": selected is not None and selected.id == row.id,
             "created_at": row.created_at} for row in rows]


@router.get("/current")
def current_target(auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    target = db.get(VacancyTarget, auth[0].id)
    row = None if target is None else db.scalar(select(VacancyAnalysis).where(
        VacancyAnalysis.id == target.vacancy_id, VacancyAnalysis.user_id == auth[0].id,
    ))
    return {"selected": False} if row is None else _response(db, auth[0], row)


@router.get("/{vacancy_id}")
def detail(vacancy_id: UUID, auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    return _response(db, auth[0], _owned(db, auth[0], vacancy_id))


@router.post("/{vacancy_id}/target")
def select_target(vacancy_id: UUID, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    row = _owned(db, auth[0], vacancy_id)
    if not row.requirements:
        raise HTTPException(422, "No mapped requirements; paste a more specific vacancy")
    target = db.get(VacancyTarget, auth[0].id)
    if target is None:
        target = VacancyTarget(user_id=auth[0].id, vacancy_id=row.id)
    else:
        target.vacancy_id = row.id
    db.add(target)
    db.flush()
    from app.curriculum import build_curriculum
    build_curriculum(db, auth[0], reason="vacancy_target")
    db.commit()
    return _response(db, auth[0], row)


@router.delete("/{vacancy_id}", status_code=204)
def delete(vacancy_id: UUID, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)):
    row = _owned(db, auth[0], vacancy_id)
    target = db.get(VacancyTarget, auth[0].id)
    if target is not None and target.vacancy_id == row.id:
        db.delete(target)
        db.flush()
        from app.curriculum import build_curriculum
        build_curriculum(db, auth[0], reason="vacancy_target_removed")
    db.delete(row)
    db.commit()
