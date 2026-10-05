"""Owned adaptive assessment flow with server-side answer validation."""
from datetime import datetime, timezone
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth import csrf_protected, current_auth
from app.assessment_content import (
    DIFFICULTY_PRIOR,
    FALLBACK_TOLERANCE,
    MAX_DIFFICULTY,
    MAX_QUESTIONS,
    MIN_DIFFICULTY,
    NEAR_SLOT_TOLERANCE,
    QUESTIONS,
    SLOT_STEP,
    skill_order,
)
from app.db.models import AssessmentResponse, AssessmentRun, AuthSession, ExerciseVersion, User
from app.db.session import get_db
from app.exercise_hints import _seed_exercise
from app.exercise_snapshots import snapshot_assessment
from app.learning import require_onboarding
from app.learning_plan import generate_plan
from app.skill_evidence import derive_assistance, record_evidence
from app.mistake_memory import record_response_mistake
from app.curriculum import build_curriculum
from app.ai_curriculum import generate_personalized_plan
from app.choice_order import ordered_choices

router=APIRouter(prefix="/assessment", tags=["assessment"])
class QuestionResponse(BaseModel):
    id:str; skill_id:str; difficulty:float; prompt:str; choices:list[str]; question_number:int; total_questions:int
class AssessmentState(BaseModel):
    status:str; completed:bool; score:float|None=None; answered:int; question:QuestionResponse|None=None
class AnswerRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    question_id:str=Field(min_length=1,max_length=80)
    answer:str=Field(min_length=1,max_length=200)
class AnswerResponse(BaseModel):
    correct:bool; feedback:str; state:AssessmentState

def _invalid_snapshot() -> HTTPException:
    return HTTPException(409, "Assessment content snapshot is unavailable")


def _snapshot_question(run: AssessmentRun, db: Session) -> dict:
    if run.current_exercise_version_id is None:
        raise _invalid_snapshot()
    version = db.get(ExerciseVersion, run.current_exercise_version_id)
    snapshot = version.content_snapshot if version is not None else None
    question = snapshot_assessment(snapshot) if isinstance(snapshot, dict) else None
    if (
        version is None
        or version.exercise_id != run.current_question_id
        or question is None
        or question.get("id") != run.current_question_id
        or not isinstance(question.get("choices"), list)
        or not isinstance(question.get("answer"), str)
        or question["answer"] not in question["choices"]
        or not isinstance(question.get("skill_id"), str)
        or not isinstance(question.get("prompt"), str)
        or not isinstance(question.get("difficulty"), (int, float))
    ):
        raise _invalid_snapshot()
    return question


def _version_for_question(db: Session, question_id: str):
    version = _seed_exercise(db, question_id)
    if version.content_snapshot is None:
        raise _invalid_snapshot()
    return version


def _question_response(q, number, session_id): return QuestionResponse(id=q["id"],skill_id=q["skill_id"],difficulty=q["difficulty"],prompt=q["prompt"],choices=ordered_choices(q["choices"],session_id=session_id,question_id=q["id"]),question_number=number,total_questions=MAX_QUESTIONS)
def _state(run, db):
    responses=db.scalars(select(AssessmentResponse).where(AssessmentResponse.run_id==run.id).order_by(AssessmentResponse.created_at)).all()
    if run.status=="completed": return AssessmentState(status=run.status,completed=True,score=(sum(r.is_correct for r in responses)/len(responses) if responses else 0),answered=len(responses))
    q=_snapshot_question(run, db)
    return AssessmentState(status=run.status,completed=False,answered=len(responses),question=_question_response(q,len(responses)+1,run.id))

def _owned_run(user,db, *, lock=False):
    query=select(AssessmentRun).where(AssessmentRun.user_id==user.id,AssessmentRun.status=="in_progress").order_by(AssessmentRun.created_at.desc())
    if lock: query=query.with_for_update()
    return db.scalar(query)

def _nearest_slot(difficulty):
    """Snap a question difficulty onto the authored graph's difficulty slots.

    The bank only knows authored questions, so the slot is the difficulty of
    the closest question in the bank.  This keeps the adaptive step aligned
    with the course order instead of drifting across unrelated questions.
    """
    return min(QUESTIONS,key=lambda q: abs(q["difficulty"]-difficulty))["difficulty"]


def _pick_question(asked, *, target_difficulty, exclude_skill_id=None):
    """Choose the next question deterministically around a target difficulty.

    Selection never repeats a question and never puts the same skill twice in a
    row, so one run cannot measure the same fact twice.  The near window is
    tried first; a wider fallback keeps the branch useful near the ends of the
    difficulty range where the window would otherwise be empty.
    """
    pool=[
        question
        for question in QUESTIONS
        if question["id"] not in asked
        and (exclude_skill_id is None or question["skill_id"]!=exclude_skill_id)
    ]
    if not pool:
        pool=[question for question in QUESTIONS if question["id"] not in asked]
    if not pool:
        return None
    for tolerance in (NEAR_SLOT_TOLERANCE,FALLBACK_TOLERANCE):
        near=[q for q in pool if abs(q["difficulty"]-target_difficulty)<=tolerance]
        if near:
            return min(near,key=lambda q: (abs(q["difficulty"]-target_difficulty),skill_order(q)))
    return min(pool,key=lambda q: (abs(q["difficulty"]-target_difficulty),skill_order(q)))


def _first_question(prior):
    """Start a run at the difficulty closest to the learner's declared level."""
    return min(QUESTIONS,key=lambda q: (abs(q["difficulty"]-prior),skill_order(q)))


def _next_target(current_difficulty, *, correct):
    """Move one authored difficulty slot up on a correct answer, down otherwise."""
    slot=_nearest_slot(current_difficulty)
    step=SLOT_STEP if correct else -SLOT_STEP
    return max(MIN_DIFFICULTY,min(MAX_DIFFICULTY,slot+step))


def _new_run(user,db):
    prior=user.profile.experience_level if user.profile else "beginner"
    target=DIFFICULTY_PRIOR.get(prior,0.15); q=_first_question(target)
    version = _version_for_question(db, q["id"])
    run=AssessmentRun(user_id=user.id,current_question_id=q["id"],current_exercise_version_id=version.id,asked_question_ids=json.dumps([q["id"]]))
    db.add(run); db.commit(); db.refresh(run); return run

@router.get("",response_model=AssessmentState)
def get_assessment(auth:tuple[User,AuthSession]=Depends(current_auth),db:Session=Depends(get_db)):
    user,_=auth
    require_onboarding(user)
    run=_owned_run(user,db)
    if run is None:
        completed=db.scalar(select(AssessmentRun).where(AssessmentRun.user_id==user.id,AssessmentRun.status=="completed").order_by(AssessmentRun.created_at.desc()))
        if completed: return _state(completed,db)
        run=_new_run(user,db)
    return _state(run,db)

@router.post("/restart", response_model=AssessmentState)
def restart(auth:tuple[User,AuthSession]=Depends(csrf_protected), db:Session=Depends(get_db)):
    user,_=auth; require_onboarding(user)
    active=_owned_run(user,db, lock=True)
    if active is not None:
        return _state(active,db)
    run=_new_run(user,db)
    return _state(run,db)

@router.post("/answers",response_model=AnswerResponse)
def answer(payload:AnswerRequest,auth:tuple[User,AuthSession]=Depends(csrf_protected),db:Session=Depends(get_db)):
    user,_=auth; require_onboarding(user); run=_owned_run(user,db, lock=True)
    if run is None: raise HTTPException(409,"Assessment is not in progress")
    if payload.question_id != run.current_question_id: raise HTTPException(409,"Question is no longer active")
    q=_snapshot_question(run, db)
    if payload.answer not in q["choices"]: raise HTTPException(422,"Choose one of the offered answers")
    correct=payload.answer==q["answer"]
    exercise_version = (
        db.get(ExerciseVersion, run.current_exercise_version_id)
    )
    if exercise_version is None:
        raise _invalid_snapshot()
    response = AssessmentResponse(
        run_id=run.id,
        exercise_version_id=exercise_version.id,
        question_id=q["id"],
        skill_id=q["skill_id"],
        difficulty=q["difficulty"],
        answer=payload.answer,
        is_correct=correct,
        created_at=datetime.now(timezone.utc),
    )
    db.add(response)
    db.flush()
    if not correct:
        record_response_mistake(
            db,
            user_id=user.id,
            source_type="assessment_response",
            source_id=response.id,
        )
    answered=len(db.scalars(select(AssessmentResponse).where(AssessmentResponse.run_id==run.id)).all())
    nxt=None
    if answered<MAX_QUESTIONS:
        asked=json.loads(run.asked_question_ids)
        target=_next_target(q["difficulty"],correct=correct)
        nxt=_pick_question(asked,target_difficulty=target,exclude_skill_id=q["skill_id"])
    if nxt is None:
        # Either the question budget is spent or the bank has nothing left that
        # is not already asked.  Both are normal endings, not a failure state.
        run.status="completed"; run.completed_at=datetime.now(timezone.utc); run.current_question_id=None; run.current_exercise_version_id=None
    else:
        next_version = _version_for_question(db, nxt["id"])
        run.current_question_id=nxt["id"]
        run.current_exercise_version_id=next_version.id
        run.asked_question_ids=json.dumps(asked+[nxt["id"]])
    if run.status == "completed":
        db.flush()
        responses = db.scalars(select(AssessmentResponse).where(AssessmentResponse.run_id == run.id)).all()
        for response in responses:
            assisted, hint_count = derive_assistance(
                db, user_id=user.id, source_type="assessment_response", source_id=str(response.id)
            )
            record_evidence(
                db, user_id=user.id, skill_id=response.skill_id,
                source_type="assessment_response", source_id=str(response.id),
                result_score=float(response.is_correct),
                assisted=assisted, hint_count=hint_count,
                occurred_at=response.created_at,
                metadata={"question_id": response.question_id, "difficulty": response.difficulty},
            )
        generate_plan(db, user, run)
        build_curriculum(db, user, reason="assessment_completed")
    db.commit(); db.refresh(run)
    if run.status == "completed":
        try:
            generate_personalized_plan(db, user, trigger="assessment_completed")
        except Exception:
            # The completed assessment and deterministic plan remain valid.
            db.rollback()
    state=_state(run,db); return AnswerResponse(correct=correct,feedback="Ответ засчитан." if correct else "Ответ неверный; следующий вопрос подберем ниже по сложности.",state=state)
