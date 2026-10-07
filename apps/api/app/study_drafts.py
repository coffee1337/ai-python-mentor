"""Owner-only unsubmitted work. A draft never submits, grades or awards credit."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.account_services import throttle
from app.auth import account_scoped_auth, account_scoped_csrf
from app.coding_exercises import validate_coding_snapshot
from app.db.models import (
    AuthSession, CodingAttempt, ExerciseVersion, KnowledgeCheckAttempt,
    KnowledgeCheckSession, LessonCompletion, LessonSession, User,
)
from app.db.product_models import LearnerProject
from app.db.reflection_models import LessonReflection
from app.db.session import get_db
from app.db.study_draft_models import StudyDraft
from app.exercise_snapshots import validate_check_snapshot
from app.learning import _lesson_from_snapshot, coding_practice_ready, require_onboarding
from app.study_progress import CourseView

router = APIRouter(prefix="/learning/drafts", tags=["study-drafts"])
DraftKind = Literal["lesson_flow", "coding", "reflection", "project_milestone"]
MAX_IDENTITIES = 500
NO_STORE = {"Cache-Control": "no-store"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DraftIdentity(StrictModel):
    kind: DraftKind
    resource_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_-]+$")
    version: int = Field(ge=0, le=2147483647)
    milestone_id: str = Field(default="", max_length=80, pattern=r"^[A-Za-z0-9_-]*$")

    @model_validator(mode="after")
    def context_shape(self):
        if self.kind == "project_milestone":
            if self.version != 0 or not self.milestone_id:
                raise ValueError("Project drafts require version 0 and a milestone")
            try:
                canonical = str(UUID(self.resource_id))
            except ValueError:
                raise ValueError("Project draft resource must be a project UUID") from None
            if canonical != self.resource_id:
                raise ValueError("Project draft UUID must use its canonical form")
        elif self.version < 1 or self.milestone_id:
            raise ValueError("Lesson drafts require a positive version and no milestone")
        return self


class FlowContent(StrictModel):
    step: int = Field(ge=1, le=3)
    answers: dict[str, str] = Field(max_length=32)

    @model_validator(mode="after")
    def bound_answers(self):
        if any(len(key) > 120 or len(value) > 1000 for key, value in self.answers.items()):
            raise ValueError("Draft answers exceed the limit")
        return self


class CodingContent(StrictModel):
    source_code: str = Field(max_length=20000)
    backup_source: str | None = Field(default=None, max_length=20000)


class ReflectionContent(StrictModel):
    text: str = Field(max_length=10000)


class ProjectContent(StrictModel):
    artifact_text: str = Field(max_length=25000)
    # An unfinished field may be invalid. It is never fetched or published here;
    # the existing submission endpoint independently validates a public URL.
    repository_url: str = Field(max_length=2048)


CONTENT_MODELS = {
    "lesson_flow": FlowContent, "coding": CodingContent,
    "reflection": ReflectionContent, "project_milestone": ProjectContent,
}


class SaveDraft(StrictModel):
    identity: DraftIdentity
    expected_revision: int = Field(ge=0, le=2147483646)
    content: dict | None


class DraftResponse(StrictModel):
    identity: DraftIdentity
    revision: int
    content: dict | None
    updated_at: datetime | None


def _error(status: int, code: str, message: str, **detail):
    return HTTPException(status, {"code": code, "message": message, **detail}, headers=NO_STORE)


def _predicate(user_id: UUID, identity: DraftIdentity):
    return (
        StudyDraft.user_id == user_id, StudyDraft.kind == identity.kind,
        StudyDraft.resource_id == identity.resource_id, StudyDraft.version == identity.version,
        StudyDraft.milestone_id == identity.milestone_id,
    )


def _row(db: Session, user_id: UUID, identity: DraftIdentity):
    return db.scalar(select(StudyDraft).where(*_predicate(user_id, identity)))


def _response(identity: DraftIdentity, row: StudyDraft | None) -> DraftResponse:
    return DraftResponse(
        identity=identity, revision=row.revision if row else 0,
        content=row.content if row else None, updated_at=row.updated_at if row else None,
    )


def _known_version(db: Session, user_id: UUID, version_id: UUID) -> bool:
    for model in (LessonSession, KnowledgeCheckSession, LessonCompletion, KnowledgeCheckAttempt, CodingAttempt, LessonReflection):
        if db.scalar(select(model.user_id).where(model.user_id == user_id, model.exercise_version_id == version_id).limit(1)):
            return True
    return False


def _context(db: Session, user: User, identity: DraftIdentity, existing: StudyDraft | None):
    """Validate persisted immutable context without invoking any publisher."""
    if identity.kind == "project_milestone":
        project = db.scalar(select(LearnerProject).where(
            LearnerProject.id == UUID(identity.resource_id), LearnerProject.user_id == user.id,
        ))
        if project is None:
            raise _error(404, "draft_context_missing", "Project not found")
        snapshot = project.template_snapshot
        milestones = snapshot.get("milestones") if isinstance(snapshot, dict) else None
        if not isinstance(milestones, list) or not any(
            isinstance(item, dict) and item.get("id") == identity.milestone_id for item in milestones
        ):
            raise _error(404, "draft_context_missing", "Project milestone not found")
        return None, project.id

    version = db.scalar(select(ExerciseVersion).where(
        ExerciseVersion.exercise_id == identity.resource_id, ExerciseVersion.version == identity.version,
    ))
    if version is None:
        raise _error(404, "draft_context_missing", "Exercise version not found")
    snapshot = version.content_snapshot
    if (not isinstance(snapshot, dict) or type(snapshot.get("schema_version")) is not int
        or snapshot["schema_version"] not in {1, 2} or snapshot.get("exercise_id") != identity.resource_id
        or type(snapshot.get("version")) is not int or snapshot["version"] != identity.version):
        raise _error(409, "draft_context_changed", "Exercise content snapshot is unavailable")
    known = (existing is not None and existing.exercise_version_id == version.id) or _known_version(db, user.id, version.id)
    if identity.kind == "coding":
        if not isinstance(version.content_snapshot, dict) or version.content_snapshot.get("kind") != "authored_python_function":
            raise _error(404, "draft_context_missing", "This coding draft format is not supported")
        contract = validate_coding_snapshot(version)
        if type(contract.get("version")) is not int:
            raise _error(409, "draft_context_changed", "Coding exercise snapshot is unavailable")
        if not known:
            # The specification GET publishes a shared coding snapshot, but no
            # coding attempt is required to save the first unfinished program.
            lesson_id = contract["lesson_id"]
            if not coding_practice_ready(db, user):
                raise _error(404, "draft_context_missing", "Complete the coding interface lessons first")
            view = CourseView(db, user, datetime.now(timezone.utc))
            resuming = view.resume is not None and view.resume["id"] == lesson_id
            lesson = view.lessons.get(lesson_id) or (view.resume if resuming else None)
            if lesson is None or (not resuming and view.status(lesson) == "locked"):
                raise _error(404, "draft_context_missing", "Exercise is not available")
            bound = db.scalar(select(LessonSession).join(
                ExerciseVersion, ExerciseVersion.id == LessonSession.exercise_version_id,
            ).where(LessonSession.user_id == user.id, LessonSession.lesson_id == lesson_id)
                .order_by(LessonSession.created_at.desc()).limit(1))
            if bound is None:
                raise _error(404, "draft_context_missing", "Open the lesson before saving a draft")
            bound_version = db.get(ExerciseVersion, bound.exercise_version_id)
            if bound_version is None or _lesson_from_snapshot(bound_version, lesson_id)["skill_id"] != contract["skill_id"]:
                raise _error(409, "draft_context_changed", "Coding draft does not match the opened lesson")
    else:
        _lesson_from_snapshot(version, identity.resource_id)
        if not known:
            raise _error(404, "draft_context_missing", "Open this lesson version before saving a draft")
    return version, None


def _content(db: Session, user: User, identity: DraftIdentity, version: ExerciseVersion | None, raw: dict | None):
    if raw is None:
        return None
    try:
        validated = CONTENT_MODELS[identity.kind].model_validate(raw)
    except ValidationError:
        # Input text, source and selected answers must not appear in error output.
        raise _error(422, "invalid_draft_content", "Draft fields or lengths are invalid") from None
    content = validated.model_dump()
    if identity.kind == "lesson_flow" and content["answers"]:
        pending = db.scalar(select(KnowledgeCheckSession.id).where(
            KnowledgeCheckSession.user_id == user.id,
            KnowledgeCheckSession.lesson_id == identity.resource_id,
            KnowledgeCheckSession.exercise_version_id == version.id,
            KnowledgeCheckSession.consumed_at.is_(None),
        ).limit(1))
        if pending is None:
            raise _error(409, "draft_context_changed", "Reload the exact knowledge check before saving its answers")
        try:
            questions = validate_check_snapshot(version.content_snapshot, identity.resource_id)
        except ValueError:
            raise _error(409, "draft_context_changed", "Knowledge check snapshot is unavailable") from None
        choices = {item["id"]: item["choices"] for item in questions}
        if any(key not in choices or value not in choices[key] for key, value in content["answers"].items()):
            raise _error(422, "invalid_draft_choices", "Draft choices do not match this knowledge check")
    return content


@router.get("", response_model=DraftResponse)
def read_draft(
    response: Response,
    kind: DraftKind = Query(), resource_id: str = Query(min_length=1, max_length=160),
    version: int = Query(ge=0, le=2147483647), milestone_id: str = Query(default="", max_length=80),
    auth: tuple[User, AuthSession] = Depends(account_scoped_auth), db: Session = Depends(get_db),
):
    response.headers.update(NO_STORE)
    require_onboarding(auth[0])
    try:
        identity = DraftIdentity(kind=kind, resource_id=resource_id, version=version, milestone_id=milestone_id)
    except ValidationError:
        raise _error(422, "invalid_draft_identity", "Draft identity is invalid") from None
    row = _row(db, auth[0].id, identity)
    _context(db, auth[0], identity, row)
    return _response(identity, row)


@router.post("", response_model=DraftResponse)
def save_draft(
    payload: SaveDraft, response: Response,
    auth: tuple[User, AuthSession] = Depends(account_scoped_csrf), db: Session = Depends(get_db),
):
    response.headers.update(NO_STORE)
    user = auth[0]
    require_onboarding(user)
    throttle(db, scope="study_draft_user", subject=str(user.id), limit=120)
    # Account deletion and new-key allocation serialize on the same owner. A
    # SQLite write lock provides the equivalent allocation boundary locally.
    if db.get_bind().dialect.name == "sqlite":
        owner_exists = db.execute(update(User).where(User.id == user.id, User.is_active.is_(True)).values(id=User.id, updated_at=User.updated_at)).rowcount == 1
    else:
        owner_exists = db.execute(select(User.id).where(User.id == user.id, User.is_active.is_(True)).with_for_update()).scalar_one_or_none() is not None
    if not owner_exists:
        raise _error(401, "draft_owner_unavailable", "The account is no longer available")
    identity = payload.identity
    previous = _row(db, user.id, identity)
    current_revision = previous.revision if previous else 0
    if current_revision != payload.expected_revision:
        raise _error(409, "draft_conflict", "This draft changed on another device", current_revision=current_revision)
    exercise_version, project_id = _context(db, user, identity, previous)
    content = _content(db, user, identity, exercise_version, payload.content)
    now = datetime.now(timezone.utc)
    if previous is None:
        count = db.scalar(select(func.count()).select_from(StudyDraft).where(StudyDraft.user_id == user.id))
        if count >= MAX_IDENTITIES:
            raise _error(409, "draft_limit", "The saved draft limit is reached; existing drafts are preserved")
        row = StudyDraft(
            user_id=user.id, **identity.model_dump(),
            exercise_version_id=exercise_version.id if exercise_version else None,
            project_id=project_id, revision=1, content=content, updated_at=now,
        )
        db.add(row)
    else:
        matched = db.execute(update(StudyDraft).where(
            *_predicate(user.id, identity), StudyDraft.revision == payload.expected_revision,
        ).values(revision=StudyDraft.revision + 1, content=content, updated_at=now)).rowcount
        if matched != 1:
            db.rollback()
            current = _row(db, user.id, identity)
            raise _error(409, "draft_conflict", "This draft changed on another device", current_revision=current.revision if current else 0)
        row = previous
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        current = _row(db, user.id, identity)
        if current is None:
            raise _error(409, "draft_context_changed", "Draft context changed; reload before saving") from None
        raise _error(409, "draft_conflict", "This draft changed on another device", current_revision=current.revision) from None
    db.refresh(row)
    return _response(identity, row)
