"""Server-graded, owned end-of-lesson knowledge checks."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import csrf_protected, current_auth
from app.db.models import AuthSession, ExerciseVersion, KnowledgeCheckAttempt, KnowledgeCheckResponse, KnowledgeCheckSession, User, UserSkill
from app.db.session import get_db
from app.exercise_hints import _seed_exercise
from app.exercise_snapshots import authored_snapshot, validate_check_snapshot
from app.learning import accessible_lesson, require_onboarding
from app.learning_plan import current_plan, generate_plan, plan_response
from app.db.models import AssessmentRun
from app.skill_evidence import derive_assistance, record_evidence
from app.mistake_memory import record_response_mistake
from app.curriculum import build_curriculum
from app.ai_curriculum import generate_personalized_plan

router=APIRouter(prefix="/learning", tags=["knowledge-check"])
PASS_SCORE=0.75
class CheckQuestion(BaseModel):
    id:str; prompt:str; choices:list[str]


class CheckExplanation(BaseModel):
    question_id: str
    explanation: str
    correct: str
    selected_explanation: str | None = None


class CheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: str
    score: float
    passed: bool
    explanations: list[CheckExplanation]
    recommendation: str
    recommended_lesson_id: str | None = None
class AnswersRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    answers:dict[str, str]

def _questions(questions):
    return [CheckQuestion(id=q["id"],prompt=q["prompt"],choices=q["choices"]) for q in questions]


def _snapshot_content(version, lesson_id: str):
    snapshot = version.content_snapshot
    lesson = snapshot.get("lesson") if isinstance(snapshot, dict) else None
    if (
        version.exercise_id != lesson_id
        or version.lesson_id != lesson_id
        or not isinstance(snapshot, dict)
        or not isinstance(lesson, dict)
        or lesson.get("id") != lesson_id
        or not isinstance(lesson.get("skill_id"), str)
        or not isinstance(snapshot, dict)
        or snapshot.get("version") != version.version
    ):
        raise HTTPException(409, "Knowledge-check content snapshot is unavailable")
    try:
        questions = validate_check_snapshot(snapshot, lesson_id)
    except (TypeError, ValueError):
        raise HTTPException(409, "Knowledge-check content snapshot is unavailable") from None
    return lesson, questions


def _persisted_exercise(db: Session, lesson_id: str):
    """Read an existing published version before consulting mutable authored data."""
    try:
        current = authored_snapshot(lesson_id)
    except ValueError:
        raise HTTPException(409, "Knowledge-check content snapshot is unavailable") from None
    version = db.scalar(
        select(ExerciseVersion).where(
            ExerciseVersion.exercise_id == lesson_id,
            ExerciseVersion.version == current["version"],
        )
    )
    return version if version is not None else _seed_exercise(db, lesson_id)


def _pending_session(db: Session, user_id, lesson_id: str) -> KnowledgeCheckSession | None:
    return db.scalar(
        select(KnowledgeCheckSession)
        .where(
            KnowledgeCheckSession.user_id == user_id,
            KnowledgeCheckSession.lesson_id == lesson_id,
            KnowledgeCheckSession.consumed_at.is_(None),
        )
        .order_by(KnowledgeCheckSession.created_at.desc())
        .limit(1)
    )


def _session_version(
    db: Session,
    session: KnowledgeCheckSession,
    lesson_id: str,
) -> ExerciseVersion:
    version = db.get(ExerciseVersion, session.exercise_version_id)
    if version is None or version.lesson_id != lesson_id:
        raise HTTPException(409, "Knowledge-check exercise version is unavailable")
    return version


def _new_session(
    db: Session,
    user_id,
    lesson_id: str,
) -> tuple[KnowledgeCheckSession, ExerciseVersion]:
    version = _persisted_exercise(db, lesson_id)
    session = KnowledgeCheckSession(
        user_id=user_id,
        lesson_id=lesson_id,
        exercise_version_id=version.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.flush()
    return session, version

@router.get("/lessons/{lesson_id}/knowledge-check",response_model=list[CheckQuestion])
def get_check(lesson_id:str,auth:tuple[User,AuthSession]=Depends(current_auth),db:Session=Depends(get_db)):
    user,_=auth
    require_onboarding(user)
    session = _pending_session(db, user.id, lesson_id)
    if session is not None:
        version = _session_version(db, session, lesson_id)
        accessible_lesson(lesson_id, db, user, bound_version=version)
        _, questions = _snapshot_content(version, lesson_id)
    else:
        accessible_lesson(lesson_id,db,user)
        session, version = _new_session(db, user.id, lesson_id)
        _, questions = _snapshot_content(version, lesson_id)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            session = _pending_session(db, user.id, lesson_id)
            if session is None:
                raise HTTPException(409, "Knowledge-check session could not be created")
            version = _session_version(db, session, lesson_id)
            _, questions = _snapshot_content(version, lesson_id)
    return _questions(questions)

@router.post("/lessons/{lesson_id}/knowledge-check",response_model=CheckResponse,status_code=201)
def submit_check(lesson_id:str,payload:AnswersRequest,auth:tuple[User,AuthSession]=Depends(csrf_protected),db:Session=Depends(get_db)):
    user,_=auth
    require_onboarding(user)
    session = _pending_session(db, user.id, lesson_id)
    if session is None:
        raise HTTPException(409, "Get the knowledge-check questions before submitting")
    exercise_version = _session_version(db, session, lesson_id)
    accessible_lesson(lesson_id, db, user, bound_version=exercise_version)
    snapshot_lesson, questions = _snapshot_content(exercise_version, lesson_id)
    if set(payload.answers) != {q["id"] for q in questions}: raise HTTPException(422,"Answer every knowledge-check question exactly once")
    rows=[]
    for q in questions:
        answer=payload.answers[q["id"]]
        if answer not in q["choices"]: raise HTTPException(422,"Choose one of the offered answers")
        rows.append((q,answer,answer==q["answer"]))
    correct=sum(item[2] for item in rows); score=correct/len(rows); passed=score>=PASS_SCORE
    attempt=KnowledgeCheckAttempt(user_id=user.id,exercise_version_id=exercise_version.id,lesson_id=lesson_id,skill_id=snapshot_lesson["skill_id"],score=score,passed=passed,created_at=datetime.now(timezone.utc))
    db.add(attempt); db.flush()
    responses = []
    for q,answer,is_correct in rows:
        response = KnowledgeCheckResponse(
            attempt_id=attempt.id,
            question_id=q["id"],
            answer=answer,
            is_correct=is_correct,
            explanation=q["explanation"],
        )
        db.add(response)
        responses.append(response)
    db.flush()
    for response in responses:
        if not response.is_correct:
            record_response_mistake(
                db,
                user_id=user.id,
                source_type="knowledge_check_response",
                source_id=response.id,
            )
    assisted, hint_count = derive_assistance(
        db, user_id=user.id, source_type="knowledge_check_attempt", source_id=str(attempt.id)
    )
    record_evidence(
        db, user_id=user.id, skill_id=snapshot_lesson["skill_id"],
        source_type="knowledge_check_attempt", source_id=str(attempt.id),
        result_score=score, assisted=assisted, hint_count=hint_count,
        occurred_at=attempt.created_at, metadata={"lesson_id": lesson_id, "passed": passed},
    )
    mastery = db.scalar(select(UserSkill).where(UserSkill.user_id == user.id, UserSkill.skill_id == snapshot_lesson["skill_id"]))
    previous_count = mastery.evidence_count - 1
    interval_days = min(14, 1 << min(previous_count, 3)) if passed else 1
    mastery.next_review_at = (attempt.created_at or datetime.now(timezone.utc)) + timedelta(days=interval_days)
    if passed:
        # Persist only the existing lesson-completion evidence; no handler recursion.
        from app.db.models import LessonCompletion
        if db.get(LessonCompletion,(user.id,lesson_id)) is None:
            db.add(LessonCompletion(
                user_id=user.id,
                lesson_id=lesson_id,
                answer="knowledge_check",
                exercise_version_id=exercise_version.id,
                evidence_type="knowledge_check_passed",
            ))
    session.consumed_at = datetime.now(timezone.utc)
    plan=current_plan(db,user); assessment_run=db.scalar(select(AssessmentRun).where(AssessmentRun.id==plan.assessment_run_id,AssessmentRun.user_id==user.id,AssessmentRun.status=="completed")) if plan else None
    if assessment_run is not None:
        generate_plan(db,user,assessment_run)
        build_curriculum(db, user, reason="evidence")
    db.commit(); db.refresh(attempt)
    try:
        generate_personalized_plan(db, user, trigger="evidence")
    except Exception:
        db.rollback()
    refreshed=plan_response(db,user) if assessment_run is not None else None
    recommended=refreshed.recommended_lesson_id if refreshed else None
    return CheckResponse(
        lesson_id=lesson_id,
        score=score,
        passed=passed,
        explanations=[
            CheckExplanation(
                question_id=q["id"],
                explanation=q["explanation"],
                correct=str(ok).lower(),
                selected_explanation=(
                    q["choice_explanations"].get(answer, q["explanation"])
                    if exercise_version.content_snapshot.get("schema_version") == 2
                    else q["explanation"]
                ),
            )
            for q, answer, ok in rows
        ],
        recommendation=(
            "Урок пройден. Персональный план обновлён."
            if passed
            else "Повторите материал урока и попробуйте проверку ещё раз."
        ),
        recommended_lesson_id=recommended,
    )
