"""Deterministic personalized plan built only from authored course content."""
import json
from datetime import datetime, timezone
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.db.models import AssessmentResponse, AssessmentRun, KnowledgeCheckAttempt, LearningPlan, LearningPlanItem, LessonCompletion, User, UserSkill
from app.learning_content import LESSONS
from app.prerequisites import PrerequisiteState, prerequisite_state
from app.skill_graph import SKILLS

# The diagnostic bank now samples every python.core skill, so an assessment
# skill normally maps to the lesson that teaches that same skill.  Legacy
# aliases stay explicit: `python.types` was taught inside the variables lesson.
ASSESSMENT_TO_SKILL = {skill["id"]: skill["id"] for skill in SKILLS}
ASSESSMENT_TO_SKILL.update(
    {
        "python.variables": "python.variables",
        "python.conditionals": "python.conditionals",
        "python.types": "python.variables",
    }
)

class SkillProfileResponse(BaseModel):
    skill_id: str
    score: float
    evidence_count: int
    next_review_at: datetime | None = None

class PlanItemResponse(BaseModel):
    lesson_id: str
    title: str
    skill_id: str
    position: int
    status: str
    completed_at: datetime | None = None
    rationale: str
    kind: str = "lesson"
    overdue_days: int | None = None

class LearningPlanResponse(BaseModel):
    status: str
    focus_skill_id: str | None
    skill_profile: list[SkillProfileResponse]
    recommendation: str
    recommended_lesson_id: str | None
    items: list[PlanItemResponse]
    assessment_run_id: str | None
    version: int | None

def _assessment_scores(db: Session, run_id):
    rows = db.scalars(select(AssessmentResponse).where(AssessmentResponse.run_id == run_id)).all()
    scores = {}
    for row in rows:
        bucket = scores.setdefault(row.skill_id, [])
        bucket.append(1.0 if row.is_correct else 0.0)
    return {skill: sum(values) / len(values) for skill, values in scores.items()}

def generate_plan(db: Session, user: User, run: AssessmentRun) -> LearningPlan:
    if run.user_id != user.id or run.status != "completed":
        raise ValueError("Only the current user's completed assessment can generate a plan")
    raw_scores = _assessment_scores(db, run.id)
    mapped_scores = {}
    for assessment_skill, score in raw_scores.items():
        lesson_skill = ASSESSMENT_TO_SKILL.get(assessment_skill)
        if lesson_skill is not None:
            mapped_scores.setdefault(lesson_skill, []).append(score)
    check_rows = db.scalars(select(KnowledgeCheckAttempt).where(KnowledgeCheckAttempt.user_id == user.id).order_by(KnowledgeCheckAttempt.created_at)).all()
    latest_checks = {}
    for attempt in check_rows:
        latest_checks[attempt.skill_id] = attempt.score
    for skill, score in latest_checks.items():
        mapped_scores.setdefault(skill, []).append(score)
    scores = {skill: sum(values) / len(values) for skill, values in mapped_scores.items()}
    existing = db.scalar(select(LearningPlan).where(LearningPlan.user_id == user.id))
    version = (existing.version + 1) if existing else 1
    if existing:
        db.execute(delete(LearningPlanItem).where(LearningPlanItem.plan_id == existing.id))
        plan = existing
        plan.assessment_run_id = run.id
        plan.version = version
    else:
        plan = LearningPlan(user_id=user.id, assessment_run_id=run.id, version=version, recommendation_text="", focus_skill_id=None)
        db.add(plan)
        db.flush()
    ordered = []
    for index, lesson in enumerate(LESSONS):
        skill = lesson["skill_id"]
        score = scores.get(skill, 0.5)
        ordered.append((1.0 - score, index, lesson, score))
    ordered.sort(key=lambda value: (-value[0], value[1]))
    readiness = prerequisite_state(db, user.id)
    completed = set(readiness.completed_lesson_ids)
    focus_lesson = next(
        (entry[2] for entry in ordered if readiness.is_lesson_ready(entry[2])),
        None,
    )
    focus = focus_lesson["skill_id"] if focus_lesson else None
    plan.focus_skill_id = focus
    next_lesson = next(
        (
            entry[2]
            for entry in ordered
            if entry[2]["id"] not in completed
            and readiness.is_lesson_ready(entry[2])
        ),
        None,
    )
    plan.recommendation_text = (
        f"Продолжите с урока «{next_lesson['title']}»: диагностика и последние проверки показывают, что навык "
        f"{next_lesson['skill_id']} требует внимания." if next_lesson else "Персональный план пока пуст."
    )
    for position, (_, _, lesson, score) in enumerate(ordered, start=1):
        rationale = "Повторите основу: в диагностике были ошибки или навык ещё не проверен." if score < 0.75 else "Закрепите навык практикой и переходите к следующей теме."
        db.add(LearningPlanItem(plan_id=plan.id, lesson_id=lesson["id"], skill_id=lesson["skill_id"], position=position, focus_score=score, rationale=rationale))
    db.flush()
    return plan

def current_plan(db: Session, user: User) -> LearningPlan | None:
    return db.scalar(select(LearningPlan).where(LearningPlan.user_id == user.id))


def _due_review_items(
    db: Session,
    user: User,
    *,
    start_position: int,
    completed_lesson_ids: set[str],
    readiness: PrerequisiteState,
) -> list[PlanItemResponse]:
    """Append retention work without reordering or replacing lesson work.

    A review is only a review after its authored lesson was completed. This
    prevents a future due date on an unstarted skill from becoming a second
    acquisition item and keeps prerequisite-ready learning ahead of retention.
    """
    now = datetime.now(timezone.utc)
    lesson_by_skill = {lesson["skill_id"]: lesson for lesson in LESSONS}
    rows = db.scalars(
        select(UserSkill)
        .where(UserSkill.user_id == user.id, UserSkill.next_review_at.is_not(None))
        .order_by(UserSkill.next_review_at.asc(), UserSkill.skill_id.asc())
    ).all()
    items: list[PlanItemResponse] = []
    for row in rows:
        lesson = lesson_by_skill.get(row.skill_id)
        if (
            lesson is None
            or lesson["id"] not in completed_lesson_ids
            or row.next_review_at is None
            or not readiness.is_skill_ready(row.skill_id)
        ):
            continue
        due_at = row.next_review_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        else:
            due_at = due_at.astimezone(timezone.utc)
        if due_at > now:
            continue
        overdue_days = max(0, (now.date() - due_at.date()).days)
        items.append(
            PlanItemResponse(
                lesson_id=lesson["id"],
                title=lesson["title"],
                skill_id=row.skill_id,
                position=start_position + len(items),
                status="review_due",
                completed_at=None,
                rationale=(
                    (
                        "Просроченное повторение добавлено после prerequisite и "
                        "учебных кандидатов; оно не снижает mastery."
                    )
                    if overdue_days
                    else (
                        "Повторение добавлено после prerequisite и учебных "
                        "кандидатов; оно показывает сохранность навыка, а не "
                        "новое освоение."
                    )
                ),
                kind="review",
                overdue_days=overdue_days,
            )
        )
    return items

def plan_response(db: Session, user: User) -> LearningPlanResponse:
    plan = current_plan(db, user)
    if plan is None:
        return LearningPlanResponse(status="assessment_required", focus_skill_id=None, skill_profile=[], recommendation="Пройдите короткую диагностику, чтобы получить персональный учебный план.", recommended_lesson_id=None, items=[], assessment_run_id=None, version=None)
    completed_run = db.scalar(select(AssessmentRun).where(AssessmentRun.id == plan.assessment_run_id, AssessmentRun.user_id == user.id, AssessmentRun.status == "completed"))
    if completed_run is None:
        return LearningPlanResponse(status="assessment_required", focus_skill_id=None, recommendation="Пройдите короткую диагностику, чтобы получить персональный учебный план.", recommended_lesson_id=None, items=[], assessment_run_id=None, version=None)
    scores = _assessment_scores(db, completed_run.id)
    mastery_rows = db.scalars(select(UserSkill).where(UserSkill.user_id == user.id)).all()
    readiness = prerequisite_state(db, user.id)
    checks = db.scalars(select(KnowledgeCheckAttempt).where(KnowledgeCheckAttempt.user_id == user.id)).all()
    latest_checks = {}
    for check in checks:
        latest_checks[check.skill_id] = check.score
    scores.update(latest_checks)
    responses = db.scalars(select(AssessmentResponse).where(AssessmentResponse.run_id == completed_run.id)).all()
    evidence = {}
    for response in responses:
        skill = response.skill_id
        evidence[skill] = evidence.get(skill, 0) + 1
    mastery_by_skill = {mastery.skill_id: mastery for mastery in mastery_rows}
    skill_profile = [SkillProfileResponse(skill_id=skill, score=score, evidence_count=(mastery_by_skill[skill].evidence_count if skill in mastery_by_skill else evidence.get(skill, 0)), next_review_at=(mastery_by_skill[skill].next_review_at if skill in mastery_by_skill else None)) for skill, score in sorted(scores.items())]
    completions = {
        row.lesson_id: row.completed_at
        for row in db.scalars(select(LessonCompletion).where(LessonCompletion.user_id == user.id)).all()
    }
    by_id = {lesson["id"]: lesson for lesson in LESSONS}
    rows = db.scalars(select(LearningPlanItem).where(LearningPlanItem.plan_id == plan.id).order_by(LearningPlanItem.position)).all()
    ordered_lessons: list[tuple[dict, str]] = []
    included: set[str] = set()
    for row in rows:
        lesson = by_id.get(row.lesson_id)
        if lesson is None or lesson["id"] in included:
            continue
        included.add(lesson["id"])
        ordered_lessons.append((lesson, row.rationale))
    # Plans created before new authored lessons are published are not rewritten;
    # newly authored lessons still appear in the live plan and snapshot flow.
    ordered_lessons.extend(
        (lesson, "Новая авторская тема, добавленная в маршрут.")
        for lesson in LESSONS
        if lesson["id"] not in included
    )
    recommended_lesson = next(
        (
            lesson
            for lesson, _ in ordered_lessons
            if lesson["id"] not in completions
            and readiness.is_lesson_ready(lesson)
        ),
        None,
    )
    items = []
    for position, (lesson, rationale) in enumerate(ordered_lessons, start=1):
        is_completed = lesson["id"] in completions
        is_ready = readiness.is_lesson_ready(lesson)
        status = (
            "completed"
            if is_completed
            else "locked"
            if not is_ready
            else "recommended"
            if recommended_lesson is not None and lesson["id"] == recommended_lesson["id"]
            else "up_next"
        )
        items.append(
            PlanItemResponse(
                lesson_id=lesson["id"],
                title=lesson["title"],
                skill_id=lesson["skill_id"],
                position=position,
                status=status,
                completed_at=completions.get(lesson["id"]),
                rationale=rationale,
            )
        )
    items.extend(
        _due_review_items(
            db,
            user,
            start_position=len(items) + 1,
            completed_lesson_ids=set(completions),
            readiness=readiness,
        )
    )
    recommended = next((item.lesson_id for item in items if item.status == "recommended"), None)
    recommendation = (
        f"Продолжите с урока «{recommended_lesson['title']}»: он следующий из доступных в вашем плане."
        if recommended_lesson
        else "Все доступные уроки пройдены. Следующие темы откроются после prerequisites."
    )
    return LearningPlanResponse(status="ready", focus_skill_id=plan.focus_skill_id, skill_profile=skill_profile, recommendation=recommendation, recommended_lesson_id=recommended, items=items, assessment_run_id=str(plan.assessment_run_id) if plan.assessment_run_id else None, version=plan.version)
