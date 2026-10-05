"""Single prerequisite-readiness policy for paths and adaptive plans."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExerciseVersion, LessonCompletion, SkillEdge, UserSkill


# Completions recorded before immutable lesson snapshots were introduced do
# not carry a trusted exercise_version_id. Keep their primary-skill meanings
# explicit rather than inferring skills from mutable or secondary graph links.
LEGACY_COMPLETION_PRIMARY_SKILLS = {
    "variables-v1": "python.variables",
    "conditions-v1": "python.conditionals",
}

MASTERY_READINESS_THRESHOLD = 0.75


def mastery_value(row: UserSkill | None) -> float:
    """Return the existing mastery projection used for prerequisite fallback."""
    if row is None or row.evidence_count == 0:
        return 0.0
    return max(
        0.0,
        min(
            1.0,
            0.45 * row.independent_score
            + 0.35 * row.knowledge_score
            + 0.20 * row.practice_score,
        ),
    )


def _primary_skill_for_completion(
    completion: LessonCompletion,
    versions: dict,
) -> str | None:
    if completion.exercise_version_id is None:
        return LEGACY_COMPLETION_PRIMARY_SKILLS.get(completion.lesson_id)

    version = versions.get(completion.exercise_version_id)
    snapshot = version.content_snapshot if version is not None else None
    lesson = snapshot.get("lesson") if isinstance(snapshot, dict) else None
    if (
        version is None
        or version.exercise_id != completion.lesson_id
        or version.lesson_id != completion.lesson_id
        or not isinstance(lesson, dict)
        or snapshot.get("schema_version") not in {1, 2}
        or isinstance(snapshot.get("schema_version"), bool)
        or snapshot.get("version") != version.version
        or lesson.get("id") != completion.lesson_id
        or not isinstance(lesson.get("skill_id"), str)
        or not lesson["skill_id"]
    ):
        return None
    return lesson["skill_id"]


@dataclass(frozen=True)
class PrerequisiteState:
    """A request-scoped view of prerequisite facts and readiness."""

    completed_lesson_ids: frozenset[str]
    completed_primary_skills: frozenset[str]
    prerequisites: dict[str, frozenset[str]]
    mastery: dict[str, float]

    def required_skills(self, skill_id: str) -> frozenset[str]:
        required: set[str] = set()
        pending = list(self.prerequisites.get(skill_id, ()))
        while pending:
            prerequisite = pending.pop()
            if prerequisite in required:
                continue
            required.add(prerequisite)
            pending.extend(self.prerequisites.get(prerequisite, ()))
        return frozenset(required)

    def is_skill_ready(self, skill_id: str) -> bool:
        # Each prerequisite may be established by either its own primary lesson
        # completion chain or by the existing mastery fallback for each
        # prerequisite. Secondary LessonSkill links are never completion
        # evidence and cannot bypass a missing lesson.
        return all(
            prerequisite in self.completed_primary_skills
            or self.mastery.get(prerequisite, 0.0) >= MASTERY_READINESS_THRESHOLD
            for prerequisite in self.required_skills(skill_id)
        )

    def is_lesson_ready(self, lesson: dict) -> bool:
        return self.is_skill_ready(lesson["skill_id"])


def prerequisite_state(db: Session, user_id) -> PrerequisiteState:
    """Resolve completion and mastery facts once for all learning surfaces."""
    # The graph is authored and seeded additively. Import locally to keep graph
    # seeding independent from this resolver.
    from app.skill_graph import seed_skill_graph

    seed_skill_graph(db)
    completions = db.scalars(
        select(LessonCompletion).where(LessonCompletion.user_id == user_id)
    ).all()
    version_ids = {
        completion.exercise_version_id
        for completion in completions
        if completion.exercise_version_id is not None
    }
    versions = (
        {
            version.id: version
            for version in db.scalars(
                select(ExerciseVersion).where(ExerciseVersion.id.in_(version_ids))
            ).all()
        }
        if version_ids
        else {}
    )
    completed_skills = {
        skill_id
        for completion in completions
        if (skill_id := _primary_skill_for_completion(completion, versions)) is not None
    }
    mastery = {
        row.skill_id: mastery_value(row)
        for row in db.scalars(select(UserSkill).where(UserSkill.user_id == user_id)).all()
    }
    prerequisites: dict[str, set[str]] = {}
    for edge in db.scalars(
        select(SkillEdge).where(SkillEdge.relation == "prerequisite")
    ):
        prerequisites.setdefault(edge.to_skill_id, set()).add(edge.from_skill_id)

    return PrerequisiteState(
        completed_lesson_ids=frozenset(
            completion.lesson_id for completion in completions
        ),
        completed_primary_skills=frozenset(completed_skills),
        prerequisites={
            skill_id: frozenset(required)
            for skill_id, required in prerequisites.items()
        },
        mastery=mastery,
    )
