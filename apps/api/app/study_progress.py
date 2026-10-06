"""Read-only learner activity and today's authored recommendations.

Facts come from persisted owned sources and append-only evidence. Reading this
module never publishes exercises, opens grading sessions, or awards credit.
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, cast, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.auth import current_auth
from app.content_publication import PUBLICATION_REPLACEMENTS
from app.db.models import (
    AssessmentResponse, AssessmentRun, AuthSession, CodingAttempt,
    CurriculumActivity, CurriculumPlanRevision, CurriculumSession,
    ExerciseVersion, Goal, KnowledgeCheckAttempt, KnowledgeCheckSession,
    LearningPlan, LearningPlanItem, LessonCompletion, LessonSession,
    ReviewAttempt, SkillEdge, SkillEvidence, User, UserSkill,
)
from app.db.session import get_db
from app.exercise_snapshots import authored_snapshot
from app.learning import _lesson_from_snapshot, require_onboarding
from app.learning_content import LESSONS
from app.prerequisites import (
    PrerequisiteState, _primary_skill_for_completion, mastery_value,
)
from app.reviews_api import _due_rows
from app.skill_graph import EDGES, SKILLS

router = APIRouter(prefix="/learning", tags=["study-progress"])
RECENT_LIMIT = 50
FOCUS_LIMIT = 6


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProgressWindow(PublicModel):
    days: Literal[7, 30]
    start_date: date
    end_date: date
    utc_offset_minutes: int


class ProgressTotals(PublicModel):
    completed_lessons: int
    total_lessons: int
    observed_skills: int
    due_reviews: int


class ProgressPeriod(PublicModel):
    active_days: int
    lessons_completed: int
    checks_attempted: int
    checks_passed: int
    coding_submissions: int
    acquisition_observations: int
    independent_observations: int
    assisted_observations: int
    review_observations: int


class ProgressDay(PublicModel):
    date: date
    activity_count: int = 0
    lessons_completed: int = 0
    acquisition_observations: int = 0
    independent_observations: int = 0
    assisted_observations: int = 0
    review_observations: int = 0
    coding_submissions: int = 0


class ProgressSkill(PublicModel):
    skill_id: str
    name: str
    knowledge_score: float | None
    practice_score: float | None
    independent_score: float | None
    retention_score: float | None
    acquisition_observations: int
    review_observations: int
    last_observed_at: datetime | None
    next_review_at: datetime | None
    lesson_id: str | None
    lesson_status: Literal["completed", "available", "locked"] | None


class RecentActivity(PublicModel):
    kind: Literal["lesson", "assessment", "knowledge_check", "coding", "review"]
    occurred_at: datetime
    skill_id: str | None
    lesson_id: str | None
    title: str
    assisted: bool | None
    hint_count: int | None
    outcome: str
    evidence_recorded: bool


class ProgressResponse(PublicModel):
    schema_version: Literal[1] = 1
    as_of: datetime
    window: ProgressWindow
    totals: ProgressTotals
    period: ProgressPeriod
    days: list[ProgressDay] = Field(max_length=30)
    skills: list[ProgressSkill]
    recent_activity: list[RecentActivity] = Field(max_length=RECENT_LIMIT)


class NextLesson(PublicModel):
    id: str
    title: str
    minutes: int
    is_resume: bool


class DueReview(PublicModel):
    skill_id: str
    scheduled_for: date
    overdue_days: int


class TodayFocus(PublicModel):
    kind: Literal["lesson", "review"]
    lesson_id: str | None
    skill_id: str
    title: str
    estimated_minutes: int
    reason_codes: list[str]


class TodayResponse(PublicModel):
    schema_version: Literal[1] = 1
    as_of: datetime
    next_lesson: NextLesson | None
    due_reviews: list[DueReview] = Field(max_length=100)
    focus: list[TodayFocus] = Field(max_length=FOCUS_LIMIT)
    estimated_minutes: int
    target_minutes: int
    source: Literal["curriculum", "starter", "course"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class CourseView:
    """Batch equivalent of path facts, using the shared prerequisite policy."""
    def __init__(self, db: Session, user: User, now: datetime):
        self.completions = list(db.scalars(select(LessonCompletion).where(
            LessonCompletion.user_id == user.id, LessonCompletion.completed_at <= now,
        )))
        self.mastery = {row.skill_id: row for row in db.scalars(select(UserSkill).where(UserSkill.user_id == user.id))}
        lesson_sessions = list(db.scalars(select(LessonSession).where(
            LessonSession.user_id == user.id, LessonSession.consumed_at.is_(None), LessonSession.created_at <= now,
        )))
        check_sessions = list(db.scalars(select(KnowledgeCheckSession).where(
            KnowledgeCheckSession.user_id == user.id, KnowledgeCheckSession.consumed_at.is_(None), KnowledgeCheckSession.created_at <= now,
        )))
        version_ids = {row.exercise_version_id for row in (*self.completions, *lesson_sessions, *check_sessions)
                       if row.exercise_version_id is not None}
        try:
            current_keys = [(lesson["id"], authored_snapshot(lesson["id"])["version"]) for lesson in LESSONS]
        except ValueError:
            raise HTTPException(409, "Lesson content snapshot is unavailable") from None
        versions = {row.id: row for row in db.scalars(select(ExerciseVersion).where(or_(
            ExerciseVersion.id.in_(version_ids),
            tuple_(ExerciseVersion.exercise_id, ExerciseVersion.version).in_(current_keys),
        )))}
        current_versions = {(row.exercise_id, row.version): row for row in versions.values()}
        completed = {row.lesson_id for row in self.completions}
        completed.update(new for old, new in PUBLICATION_REPLACEMENTS.items() if old in completed)
        primary = {skill for row in self.completions if (skill := _primary_skill_for_completion(row, versions)) is not None}
        prerequisites: dict[str, set[str]] = {}
        edges = set(tuple(item) for item in EDGES)
        edges.update(db.execute(select(SkillEdge.from_skill_id, SkillEdge.to_skill_id, SkillEdge.relation)))
        for source, target, relation in edges:
            if relation == "prerequisite":
                prerequisites.setdefault(target, set()).add(source)
        self.readiness = PrerequisiteState(
            frozenset(completed), frozenset(primary),
            {skill: frozenset(required) for skill, required in prerequisites.items()},
            {skill: mastery_value(row) for skill, row in self.mastery.items()},
        )
        # A lesson binding has precedence over the check binding, as in learning_path.
        self.pending = {row.lesson_id: row for row in check_sessions}
        self.pending.update({row.lesson_id: row for row in lesson_sessions})
        self.lessons = {}
        for authored, current_key in zip(LESSONS, current_keys, strict=True):
            pending = self.pending.get(authored["id"])
            if pending is not None:
                version = versions.get(pending.exercise_version_id)
                if version is None:
                    raise HTTPException(409, "Lesson content snapshot is unavailable")
                lesson = _lesson_from_snapshot(version, authored["id"])
            elif (version := current_versions.get(current_key)) is not None:
                lesson = _lesson_from_snapshot(version, authored["id"])
            else:
                lesson = authored
            self.lessons[lesson["id"]] = lesson
        self.plan = db.scalar(select(LearningPlan).where(LearningPlan.user_id == user.id))
        order = {}
        if self.plan is not None:
            order = {PUBLICATION_REPLACEMENTS.get(row.lesson_id, row.lesson_id): row.position
                     for row in db.scalars(select(LearningPlanItem).where(LearningPlanItem.plan_id == self.plan.id))}
        ordered = sorted(self.lessons.values(), key=lambda lesson: order.get(lesson["id"], len(order) + 1))
        self.next = next((lesson for lesson in ordered if self.status(lesson) == "available"), None)
        # Resume historical publications only under the established alias policy.
        historical = [row for row in (*lesson_sessions, *check_sessions)
                      if row.lesson_id in PUBLICATION_REPLACEMENTS
                      and row.lesson_id not in completed
                      and PUBLICATION_REPLACEMENTS[row.lesson_id] not in completed]
        self.resume = None
        if historical:
            row = max(historical, key=lambda item: item.created_at)
            version = versions.get(row.exercise_version_id)
            if version is None:
                raise HTTPException(409, "Lesson content snapshot is unavailable")
            self.resume = _lesson_from_snapshot(version, row.lesson_id)

    def status(self, lesson: dict) -> str:
        if lesson["id"] in self.readiness.completed_lesson_ids:
            return "completed"
        return "available" if self.readiness.is_lesson_ready(lesson) else "locked"


def _calendar_column(db: Session, column, offset: int):
    if db.get_bind().dialect.name == "sqlite":
        return func.date(column, f"{offset:+d} minutes")
    # Timestamp columns are timestamptz on PostgreSQL. Group by a fixed offset,
    # independent of the connection timezone and daylight-saving transitions.
    return cast(func.timezone("UTC", column) + timedelta(minutes=offset), Date)


def _day_key(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _period_counts(db: Session, user: User, start: datetime, now: datetime, offset: int, calendar: dict):
    totals = dict(lessons_completed=0, checks_attempted=0, checks_passed=0,
                  coding_submissions=0, acquisition_observations=0,
                  independent_observations=0, assisted_observations=0, review_observations=0)
    sources = (
        (LessonCompletion, LessonCompletion.completed_at, "lessons_completed"),
        (CodingAttempt, CodingAttempt.created_at, "coding_submissions"),
        (KnowledgeCheckAttempt, KnowledgeCheckAttempt.created_at, "checks_attempted"),
        (ReviewAttempt, ReviewAttempt.occurred_at, None),
    )
    for model, timestamp, key in sources:
        day = _calendar_column(db, timestamp, offset)
        for day_value, count in db.execute(select(day, func.count()).where(
            model.user_id == user.id, timestamp >= start, timestamp <= now,
        ).group_by(day)):
            key_date = _day_key(day_value)
            calendar[key_date]["activity_count"] += count
            if key is not None:
                totals[key] += count
            if key in calendar[key_date]:
                calendar[key_date][key] += count
    totals["checks_passed"] = db.scalar(select(func.count()).select_from(KnowledgeCheckAttempt).where(
        KnowledgeCheckAttempt.user_id == user.id, KnowledgeCheckAttempt.created_at >= start,
        KnowledgeCheckAttempt.created_at <= now, KnowledgeCheckAttempt.passed.is_(True),
    )) or 0
    assessment_day = _calendar_column(db, AssessmentResponse.created_at, offset)
    for day_value, count in db.execute(select(assessment_day, func.count()).join(
        AssessmentRun, AssessmentRun.id == AssessmentResponse.run_id,
    ).where(AssessmentRun.user_id == user.id, AssessmentResponse.created_at >= start,
            AssessmentResponse.created_at <= now).group_by(assessment_day)):
        calendar[_day_key(day_value)]["activity_count"] += count
    day = _calendar_column(db, SkillEvidence.occurred_at, offset)
    for day_value, retention, assisted, count in db.execute(select(
        day, SkillEvidence.retention_only, SkillEvidence.assisted, func.count(),
    ).where(SkillEvidence.user_id == user.id, SkillEvidence.occurred_at >= start,
            SkillEvidence.occurred_at <= now).group_by(day, SkillEvidence.retention_only, SkillEvidence.assisted)):
        key_date = _day_key(day_value)
        keys = ["review_observations"] if retention else ["acquisition_observations", "assisted_observations" if assisted else "independent_observations"]
        for key in keys:
            totals[key] += count
            calendar[key_date][key] += count
    return {"active_days": sum(item["activity_count"] > 0 for item in calendar.values()), **totals}


def _snapshot_identity(snapshot, exercise_id, version_number):
    return (isinstance(snapshot, dict) and type(snapshot.get("schema_version")) is int
            and snapshot["schema_version"] in {1, 2}
            and snapshot.get("exercise_id") == exercise_id
            and snapshot.get("version") == version_number)


def _public_history_identity(snapshot, exercise_id, version_number, version_lesson_id, expected_lesson=None):
    """Read only public identity/title from the exact source snapshot."""
    if not _snapshot_identity(snapshot, exercise_id, version_number):
        return None, None, None
    lesson = snapshot.get("lesson")
    if isinstance(lesson, dict) and lesson.get("id") == version_lesson_id and (
        expected_lesson is None or lesson.get("id") == expected_lesson
    ):
        skill = lesson.get("skill_id") if isinstance(lesson.get("skill_id"), str) else None
        title = lesson.get("title") if isinstance(lesson.get("title"), str) else None
        return lesson["id"], skill, title
    return None, None, None


def _recent_activity(db: Session, user: User, start: datetime, now: datetime):
    events = []
    evidence_by_source = {}
    # At most 50 records from each source can contribute to the merged last 50.
    source_specs = (
        ("lesson", LessonCompletion, LessonCompletion.completed_at, None),
        ("assessment", AssessmentResponse, AssessmentResponse.created_at, "assessment_response"),
        ("knowledge_check", KnowledgeCheckAttempt, KnowledgeCheckAttempt.created_at, "knowledge_check_attempt"),
        ("coding", CodingAttempt, CodingAttempt.created_at, "coding_attempt"),
        ("review", ReviewAttempt, ReviewAttempt.occurred_at, "review_attempt"),
    )
    recent_rows = []
    for kind, model, timestamp, source_type in source_specs:
        # Explicit columns prevent private answers, source code and evidence
        # metadata from becoming part of the public-history read projection.
        columns = [timestamp.label("event_at"), model.exercise_version_id,
                   ExerciseVersion.exercise_id.label("version_exercise_id"),
                   ExerciseVersion.version.label("version_number"),
                   ExerciseVersion.lesson_id.label("version_lesson_id"), ExerciseVersion.content_snapshot]
        if kind == "lesson":
            columns += [model.lesson_id, model.evidence_type]
        else:
            columns += [model.id.label("source_id"), model.skill_id] if kind != "coding" else [model.id.label("source_id"), model.exercise_id, model.status]
            if kind == "assessment":
                columns += [model.question_id, model.is_correct]
            elif kind == "knowledge_check":
                columns += [model.lesson_id, model.passed]
        query = select(*columns).select_from(model).outerjoin(ExerciseVersion, ExerciseVersion.id == model.exercise_version_id)
        if kind == "assessment":
            query = query.join(AssessmentRun, AssessmentRun.id == model.run_id).where(AssessmentRun.user_id == user.id)
        else:
            query = query.where(model.user_id == user.id)
        tie = model.lesson_id if kind == "lesson" else model.id
        rows = list(db.execute(query.where(timestamp >= start, timestamp <= now).order_by(timestamp.desc(), tie.desc()).limit(RECENT_LIMIT)).mappings())
        recent_rows.extend((kind, source_type, row) for row in rows)
    source_ids = [str(row["source_id"]) for _, source_type, row in recent_rows if source_type]
    if source_ids:
        for row in db.execute(select(SkillEvidence.source_type, SkillEvidence.source_id,
            SkillEvidence.assisted, SkillEvidence.hint_count, SkillEvidence.result_score,
        ).where(SkillEvidence.user_id == user.id, SkillEvidence.source_id.in_(source_ids), SkillEvidence.occurred_at <= now)):
            evidence_by_source[(row.source_type, row.source_id)] = row
    names = {item["id"]: item["name"] for item in SKILLS}
    for kind, source_type, row in recent_rows:
        lesson_id, mapped_skill, title = _public_history_identity(
            row["content_snapshot"], row["version_exercise_id"], row["version_number"], row["version_lesson_id"], row.get("lesson_id"),
        )
        skill = mapped_skill or row.get("skill_id")
        evidence = evidence_by_source.get((source_type, str(row.get("source_id"))))
        if kind == "lesson":
            # NULL-version legacy completion is a fact, but not a title for a
            # newly published lesson. Keep a neutral title when unavailable.
            lesson_id = lesson_id or row["lesson_id"]
            outcome = "completed"
        elif kind == "assessment":
            lesson_id = None
            title = f"Диагностика: {names.get(skill, 'навык')}"
            outcome = "correct" if row["is_correct"] else "incorrect"
        elif kind == "knowledge_check":
            lesson_id = lesson_id or row["lesson_id"]
            outcome = "passed" if row["passed"] else "failed"
        elif kind == "coding":
            outcome = row["status"]
            title = title or "Задание с кодом"
        else:
            outcome = "correct" if evidence and evidence.result_score == 1 else "partial" if evidence and evidence.result_score > 0 else "incorrect"
            title = title or f"Повторение: {names.get(skill, 'навык')}"
        events.append({"kind": kind, "occurred_at": _utc(row["event_at"]), "skill_id": skill,
                       "lesson_id": lesson_id, "title": title or "Пройденный урок",
                       "assisted": evidence.assisted if evidence else None,
                       "hint_count": evidence.hint_count if evidence else None,
                       "outcome": outcome, "evidence_recorded": evidence is not None})
    return sorted(events, key=lambda item: item["occurred_at"], reverse=True)[:RECENT_LIMIT]


@router.get("/progress", response_model=ProgressResponse)
def progress(days: int = Query(default=7, ge=7, le=30, json_schema_extra={"enum": [7, 30]}),
             utc_offset_minutes: int = Query(default=0, ge=-840, le=840),
             auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    if days not in {7, 30}:
        raise HTTPException(422, "days must be 7 or 30")
    now = _utc_now()
    end_date = (now + timedelta(minutes=utc_offset_minutes)).date()
    start_date = end_date - timedelta(days=days - 1)
    start = datetime.combine(start_date, time.min, tzinfo=timezone.utc) - timedelta(minutes=utc_offset_minutes)
    calendar = {start_date + timedelta(days=index): {
        "date": start_date + timedelta(days=index), "activity_count": 0, "lessons_completed": 0,
        "acquisition_observations": 0, "independent_observations": 0,
        "assisted_observations": 0, "review_observations": 0, "coding_submissions": 0,
    } for index in range(days)}
    course = CourseView(db, user, now)
    counts = {}
    for skill, retention, count, last in db.execute(select(
        SkillEvidence.skill_id, SkillEvidence.retention_only, func.count(), func.max(SkillEvidence.occurred_at),
    ).where(SkillEvidence.user_id == user.id, SkillEvidence.occurred_at <= now).group_by(SkillEvidence.skill_id, SkillEvidence.retention_only)):
        item = counts.setdefault(skill, {"acquisition": 0, "review": 0, "last": None})
        item["review" if retention else "acquisition"] = count
        observed_at = _utc(last)
        item["last"] = max(item["last"], observed_at) if item["last"] else observed_at
    by_skill = {lesson["skill_id"]: lesson for lesson in course.lessons.values()}
    skills = []
    for authored in SKILLS:
        skill = authored["id"]
        item = counts.get(skill, {"acquisition": 0, "review": 0, "last": None})
        row = course.mastery.get(skill)
        lesson = by_skill.get(skill)
        acquisition_known = row is not None and item["acquisition"] > 0
        retention_known = row is not None and item["review"] > 0
        skills.append({"skill_id": skill, "name": authored["name"],
            "knowledge_score": row.knowledge_score if acquisition_known else None,
            "practice_score": row.practice_score if acquisition_known else None,
            "independent_score": row.independent_score if acquisition_known else None,
            "retention_score": row.retention_score if retention_known else None,
            "acquisition_observations": item["acquisition"], "review_observations": item["review"],
            "last_observed_at": item["last"], "next_review_at": _utc(row.next_review_at) if row and row.next_review_at else None,
            "lesson_id": lesson["id"] if lesson else None, "lesson_status": course.status(lesson) if lesson else None})
    return {"schema_version": 1, "as_of": now,
        "window": {"days": days, "start_date": start_date, "end_date": end_date, "utc_offset_minutes": utc_offset_minutes},
        "totals": {"completed_lessons": sum(course.status(lesson) == "completed" for lesson in course.lessons.values()),
                   "total_lessons": len(course.lessons), "observed_skills": len(counts), "due_reviews": len(_due_rows(db, user, now=now))},
        "period": _period_counts(db, user, start, now, utc_offset_minutes, calendar),
        "days": list(calendar.values()), "skills": skills,
        "recent_activity": _recent_activity(db, user, start, now)}


@router.get("/today", response_model=TodayResponse)
def today(auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    now = _utc_now()
    course = CourseView(db, user, now)
    due = _due_rows(db, user, now=now)[:100]
    due_skill_ids = {row.skill_id for row, _ in due}
    due_reviews = [{"skill_id": row.skill_id, "scheduled_for": due_at.date(),
                    "overdue_days": min(36500, max(0, (now.date() - due_at.date()).days))} for row, due_at in due]
    next_item = course.resume or course.next
    goal = db.scalar(select(Goal).where(Goal.user_id == user.id))
    target = min(60, max(0, goal.weekly_minutes if goal else 0))
    focus = []
    source = "course" if course.plan else "starter"
    revision = db.scalar(select(CurriculumPlanRevision).where(
        CurriculumPlanRevision.plan_id == course.plan.id, CurriculumPlanRevision.as_of <= now,
    ).order_by(CurriculumPlanRevision.version.desc()).limit(1)) if course.plan else None
    if revision is not None:
        session = db.scalar(select(CurriculumSession).where(CurriculumSession.revision_id == revision.id).order_by(CurriculumSession.position).limit(1))
        if session is not None:
            target = min(60, max(0, session.target_minutes))
            for item in db.scalars(select(CurriculumActivity).where(CurriculumActivity.session_id == session.id).order_by(CurriculumActivity.position).limit(100)):
                lesson = course.lessons.get(item.lesson_id)
                if (item.kind not in {"lesson", "review"} or item.availability != "available"
                    or lesson is None or lesson["skill_id"] != item.skill_id or item.estimated_minutes <= 0
                    or not course.readiness.is_lesson_ready(lesson)):
                    continue
                if item.kind == "lesson" and course.status(lesson) != "available":
                    continue
                if item.kind == "review" and item.skill_id not in due_skill_ids:
                    continue
                if any(entry["kind"] == item.kind and entry["skill_id"] == item.skill_id for entry in focus):
                    continue
                minutes = min(60, item.estimated_minutes)
                if sum(entry["estimated_minutes"] for entry in focus) + minutes > target:
                    continue
                focus.append({"kind": item.kind, "lesson_id": lesson["id"], "skill_id": item.skill_id,
                              "title": lesson["title"], "estimated_minutes": minutes,
                              "reason_codes": [code for code in item.reason_codes if isinstance(code, str)][:20]})
                if len(focus) == FOCUS_LIMIT:
                    break
            if focus:
                source = "curriculum"
    if course.resume:
        # Stable pending historical publication precedes fresh recommendations.
        focus = []
    if not focus and next_item:
        focus.append({"kind": "lesson", "lesson_id": next_item["id"], "skill_id": next_item["skill_id"],
                      "title": next_item["title"], "estimated_minutes": next_item["minutes"],
                      "reason_codes": ["resume_publication" if course.resume else "next_available_lesson"]})
        source = "course" if course.plan else "starter"
    if not focus and due:
        by_skill = {lesson["skill_id"]: lesson for lesson in course.lessons.values()}
        for row, _ in due:
            lesson = by_skill.get(row.skill_id)
            if lesson and course.readiness.is_lesson_ready(lesson):
                if sum(item["estimated_minutes"] for item in focus) + lesson["minutes"] > target:
                    continue
                focus.append({"kind": "review", "lesson_id": lesson["id"], "skill_id": row.skill_id,
                              "title": lesson["title"], "estimated_minutes": lesson["minutes"], "reason_codes": ["review_due"]})
                if len(focus) == FOCUS_LIMIT:
                    break
    return {"schema_version": 1, "as_of": now, "next_lesson": {
        "id": next_item["id"], "title": next_item["title"], "minutes": next_item["minutes"], "is_resume": course.resume is not None,
    } if next_item else None, "due_reviews": due_reviews, "focus": focus,
        "estimated_minutes": sum(item["estimated_minutes"] for item in focus), "target_minutes": target, "source": source}
