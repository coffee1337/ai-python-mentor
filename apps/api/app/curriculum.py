"""Deterministic, explainable curriculum planning over authored content."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CurriculumActivity, CurriculumPlanRevision, CurriculumSession, Goal,
    LearningPlan, LearningPlanItem, LessonCompletion, Skill,
    User, UserSkill,
)
from app.learning_content import LESSONS
from app.skill_graph import seed_skill_graph
from app.prerequisites import PrerequisiteState, mastery_value, prerequisite_state

POLICY_VERSION = "curriculum-v1"
MIN_SESSION = 20
MAX_SESSION = 60
MAX_REVIEW_PRIORITY = 0.30


def _mastery(row: UserSkill | None) -> float:
    return mastery_value(row)


def _review_candidates(
    db: Session,
    user: User,
    *,
    completed: set[str],
    readiness: PrerequisiteState,
    lesson_order: dict[str, int],
) -> list[tuple[float, int, dict, list[str]]]:
    """Return due reviews after prerequisite-ready lesson candidates.

    Review priority is deliberately capped. Reviews are selected only after
    lesson candidates, so overdue retention work cannot displace a prerequisite
    or a higher-priority acquisition item.
    """
    now = datetime.now(timezone.utc)
    lesson_by_skill = {lesson["skill_id"]: lesson for lesson in LESSONS}
    candidates: list[tuple[float, int, dict, list[str]]] = []
    for row in db.scalars(
        select(UserSkill).where(
            UserSkill.user_id == user.id,
            UserSkill.next_review_at.is_not(None),
        )
    ):
        lesson = lesson_by_skill.get(row.skill_id)
        if lesson is None or lesson["id"] not in completed or row.next_review_at is None:
            continue
        due_at = row.next_review_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        else:
            due_at = due_at.astimezone(timezone.utc)
        if due_at > now:
            continue
        if not readiness.is_skill_ready(row.skill_id):
            continue
        overdue_days = max(0, (now.date() - due_at.date()).days)
        priority = min(MAX_REVIEW_PRIORITY, 0.20 + 0.02 * min(overdue_days, 5))
        reasons = ["review_due"]
        if overdue_days:
            reasons.append("review_overdue")
        candidates.append(
            (
                round(priority, 6),
                lesson_order[lesson["id"]],
                lesson,
                reasons,
            )
        )
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]["skill_id"], item[2]["id"]))
    return candidates


def build_curriculum(db: Session, user: User, *, reason: str = "evidence") -> CurriculumPlanRevision | None:
    """Create an immutable revision and switch the legacy plan pointer in one caller-owned transaction."""
    plan = db.scalar(select(LearningPlan).where(LearningPlan.user_id == user.id))
    if plan is None:
        return None
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    seed_skill_graph(db)
    goal = db.scalar(select(Goal).where(Goal.user_id == user.id))
    mastery = {row.skill_id: row for row in db.scalars(select(UserSkill).where(UserSkill.user_id == user.id))}
    readiness = prerequisite_state(db, user.id)
    completed = set(readiness.completed_lesson_ids)
    lesson_order = {lesson["id"]: index for index, lesson in enumerate(LESSONS)}
    candidates = []
    unavailable = 0
    goal_text = (goal.target_role if goal else "").lower()
    for lesson in LESSONS:
        if lesson["id"] in completed:
            continue
        skill_id = lesson["skill_id"]
        if not readiness.is_skill_ready(skill_id):
            continue
        skill = db.get(Skill, skill_id)
        if skill is None:
            unavailable += 1
            continue
        row = mastery.get(skill_id)
        gap = 1.0 - _mastery(row)
        now = datetime.now(timezone.utc)
        next_review = row.next_review_at if row else None
        last_practiced = row.last_practiced_at if row else None
        if next_review is not None and next_review.tzinfo is None:
            next_review = next_review.replace(tzinfo=timezone.utc)
        if last_practiced is not None and last_practiced.tzinfo is None:
            last_practiced = last_practiced.replace(tzinfo=timezone.utc)
        review_due = bool(next_review and next_review <= now)
        stale = bool(last_practiced and (now - last_practiced).days >= 30)
        due = review_due or stale
        goal_fit = "backend" in goal_text and skill.category.startswith("backend.")
        priority = round(
            0.40 * gap
            + 0.30 * skill.importance
            + 0.15 * float(due)
            + 0.10 * skill.difficulty
            + 0.05 * float(goal_fit),
            6,
        )
        reasons = ["skill_gap"] if gap > 0 else []
        if review_due:
            reasons.append("review_due")
        elif stale:
            reasons.append("stale_evidence")
        reasons.append("goal_fit_matched" if goal_fit else "goal_fit_unknown")
        if row is None or row.evidence_count == 0:
            reasons.append("unassessed")
        candidates.append((priority, lesson_order[lesson["id"]], lesson, reasons))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]["skill_id"], item[2]["id"]))
    weekly = max(0, goal.weekly_minutes if goal else 0)
    budget = min(MAX_SESSION, weekly) if weekly else 0
    # A valid onboarding budget may be 15..19; don't misreport 20 minutes as
    # available. Mark coverage as insufficient rather than fabricate duration.
    session_minutes = min(MAX_SESSION, budget) if budget >= MIN_SESSION else 0
    review_candidates = _review_candidates(
        db,
        user,
        completed=completed,
        readiness=readiness,
        lesson_order=lesson_order,
    )
    selected: list[tuple[str, float, dict, list[str]]] = []
    used = 0
    for priority, _, lesson, reasons in candidates:
        if used + 10 > session_minutes and selected:
            break
        selected.append(("lesson", priority, lesson, reasons))
        used += 10
    if used < session_minutes:
        for priority, _, lesson, reasons in review_candidates:
            if used + 10 > session_minutes:
                break
            selected.append(("review", priority, lesson, reasons))
            used += 10
    version = (db.scalar(select(CurriculumPlanRevision.version).where(
        CurriculumPlanRevision.plan_id == plan.id
    ).order_by(CurriculumPlanRevision.version.desc())) or 0) + 1
    legacy_revision_exists = db.scalar(select(CurriculumPlanRevision.id).where(
        CurriculumPlanRevision.plan_id == plan.id,
        CurriculumPlanRevision.reason == "legacy_import",
    ).limit(1))
    if legacy_revision_exists is None and version == 1:
        legacy = CurriculumPlanRevision(
            plan_id=plan.id, version=version, policy_version="legacy-import",
            as_of=plan.generated_at,
            goal_snapshot={"target_role": goal.target_role if goal else None, "weekly_minutes": goal.weekly_minutes if goal else 0},
            coverage={"source": "existing_learning_plan", "vacancy_fit": "unavailable"},
            reason="legacy_import",
        )
        db.add(legacy)
        db.flush()
        legacy_session = CurriculumSession(
            revision_id=legacy.id, position=1, target_minutes=0, planned_minutes=0,
            rationale="Импортированы существующие рекомендации; длительность источника не указана.",
        )
        db.add(legacy_session)
        db.flush()
        old_items = db.scalars(select(LearningPlanItem).where(LearningPlanItem.plan_id == plan.id).order_by(LearningPlanItem.position)).all()
        for position, item in enumerate(old_items, start=1):
            db.add(CurriculumActivity(
                session_id=legacy_session.id, position=position, kind="lesson",
                lesson_id=item.lesson_id, skill_id=item.skill_id, estimated_minutes=0,
                priority=item.focus_score, reason_codes=["legacy_import"], availability="legacy",
            ))
        version += 1
    revision = CurriculumPlanRevision(
        plan_id=plan.id, version=version, policy_version=POLICY_VERSION,
        as_of=datetime.now(timezone.utc),
        goal_snapshot={"target_role": goal.target_role if goal else None, "weekly_minutes": weekly},
        coverage={
            "vacancy_fit": "unavailable", "practice": "unavailable",
            "review": "scheduled" if any(kind == "review" for kind, *_ in selected) else "available" if review_candidates else "unavailable",
            "unavailable_lessons": unavailable,
            "session": "scheduled" if used >= MIN_SESSION else "insufficient_authored_content",
        },
        reason=reason,
    )
    db.add(revision)
    db.flush()
    if session_minutes:
        target = session_minutes
        session = CurriculumSession(
            revision_id=revision.id, position=1, target_minutes=target, planned_minutes=used,
            rationale="Новые авторские уроки отсортированы по gap, важности навыка и доступности prerequisite.",
        )
        db.add(session)
        db.flush()
        for position, (kind, priority, lesson, reasons) in enumerate(selected, start=1):
            db.add(CurriculumActivity(
                session_id=session.id, position=position, kind=kind,
                lesson_id=lesson["id"], skill_id=lesson["skill_id"], estimated_minutes=lesson["minutes"],
                priority=priority, reason_codes=reasons,
            ))
    db.flush()
    return revision


def curriculum_response(db: Session, user: User) -> dict:
    plan = db.scalar(select(LearningPlan).where(LearningPlan.user_id == user.id))
    if plan is None:
        return {"revision_id": None, "as_of": None, "coverage": {}, "sessions": []}
    readiness = prerequisite_state(db, user.id)
    lesson_by_id = {lesson["id"]: lesson for lesson in LESSONS}
    revision = db.scalar(select(CurriculumPlanRevision).where(
        CurriculumPlanRevision.plan_id == plan.id
    ).order_by(CurriculumPlanRevision.version.desc()))
    if revision is None:
        return {"revision_id": None, "as_of": None, "coverage": {}, "sessions": []}
    sessions = []
    for session in db.scalars(select(CurriculumSession).where(CurriculumSession.revision_id == revision.id).order_by(CurriculumSession.position)):
        activities = db.scalars(select(CurriculumActivity).where(CurriculumActivity.session_id == session.id).order_by(CurriculumActivity.position)).all()
        sessions.append({
            "position": session.position, "target_minutes": session.target_minutes,
            "planned_minutes": session.planned_minutes, "status": session.status,
            "rationale": session.rationale,
            "activities": [{
                "kind": item.kind, "lesson_id": item.lesson_id, "skill_id": item.skill_id,
                "estimated_minutes": item.estimated_minutes, "priority": item.priority,
                "reason_codes": item.reason_codes,
                "availability": (
                    "locked"
                    if item.kind == "lesson"
                    and item.lesson_id in lesson_by_id
                    and item.lesson_id not in readiness.completed_lesson_ids
                    and not readiness.is_lesson_ready(lesson_by_id[item.lesson_id])
                    else item.availability
                ),
            } for item in activities],
        })
    return {"revision_id": str(revision.id), "version": revision.version, "as_of": revision.as_of, "coverage": revision.coverage, "sessions": sessions}
