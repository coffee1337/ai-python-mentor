from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_auth
from app.db.models import AuthSession, LessonSkill, Skill, SkillEdge, User
from app.db.session import get_db
from app.learning import require_onboarding
from app.skill_graph import seed_skill_graph

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillResponse(BaseModel):
    id: str
    name: str
    category: str
    difficulty: float
    description: str
    importance: float
    tags: list[str]
    prerequisites: list[str]
    lesson_ids: list[str]


class SkillGraphResponse(BaseModel):
    skills: list[SkillResponse]
    edges: list[dict[str, str]]


def _read_graph(db: Session):
    seed_skill_graph(db)
    db.commit()
    return (
        db.scalars(select(Skill).order_by(Skill.category, Skill.difficulty, Skill.id)).all(),
        db.scalars(select(SkillEdge).order_by(SkillEdge.from_skill_id, SkillEdge.to_skill_id)).all(),
        db.scalars(select(LessonSkill).order_by(LessonSkill.lesson_id, LessonSkill.skill_id)).all(),
    )


def _responses(skills, edges, links):
    prerequisites: dict[str, list[str]] = {}
    for edge in edges:
        if edge.relation == "prerequisite":
            prerequisites.setdefault(edge.to_skill_id, []).append(edge.from_skill_id)
    lessons: dict[str, list[str]] = {}
    for link in links:
        lessons.setdefault(link.skill_id, []).append(link.lesson_id)
    return [
        SkillResponse(
            id=skill.id,
            name=skill.name,
            category=skill.category,
            difficulty=skill.difficulty,
            description=skill.description,
            importance=skill.importance,
            tags=skill.tags,
            prerequisites=prerequisites.get(skill.id, []),
            lesson_ids=lessons.get(skill.id, []),
        )
        for skill in skills
    ]


@router.get("", response_model=list[SkillResponse])
def get_skills(auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    require_onboarding(auth[0])
    skills, edges, links = _read_graph(db)
    return _responses(skills, edges, links)


@router.get("/graph", response_model=SkillGraphResponse)
def get_graph(auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    require_onboarding(auth[0])
    skills, edges, links = _read_graph(db)
    return SkillGraphResponse(
        skills=_responses(skills, edges, links),
        edges=[{"from": edge.from_skill_id, "to": edge.to_skill_id, "relation": edge.relation} for edge in edges],
    )


@router.get("/{skill_id}", response_model=SkillResponse)
def get_skill(skill_id: str, auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    require_onboarding(auth[0])
    skills, edges, links = _read_graph(db)
    skill = next((item for item in skills if item.id == skill_id), None)
    if skill is None:
        raise HTTPException(404, "Skill not found")
    return _responses([skill], edges, links)[0]
