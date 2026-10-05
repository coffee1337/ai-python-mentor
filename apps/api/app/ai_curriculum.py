"""Server-side AI curriculum generation with strict domain validation."""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from threading import Lock
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import ai_gateway
from app.db.models import (
    AIPlanCurrent, AIPlanGeneration, AIPlanStep, AIUsageLedger, CurriculumPlanRevision,
    AssessmentResponse, AssessmentRun, Goal, LearningPlan, LessonCompletion,
    Skill, SkillEdge, User, UserSkill,
)
from app.learning_content import LESSONS

MODEL_ID = "gpt-6-luna"
PROMPT_VERSION = "ai-curriculum-v1"
SCHEMA_VERSION = "ai-curriculum-output-v1"
MAX_STEPS = 5
MAX_OUTPUT_CHARS = 30000
ALLOWED_DURATIONS = {5, 10, 15, 20, 25, 30}


class GeneratedLesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=1200)
    example_code: str = Field(default="", max_length=1200)

    @field_validator("title", "explanation", "example_code")
    @classmethod
    def no_solution_text(cls, value: str) -> str:
        if any(marker in value.lower() for marker in ("solution:", "answer:", "решение:", "правильный ответ")):
            raise ValueError("solution text is not allowed")
        return value


class GeneratedExercise(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=1200)
    expected_result: str = Field(min_length=1, max_length=700)
    submission_type: str
    starter_code: str | None = Field(default=None, max_length=3000)
    constraints: list[str] = Field(default_factory=list, max_length=6)
    evaluation_criteria: list[str] = Field(min_length=1, max_length=6)
    success_criteria: list[str] = Field(min_length=1, max_length=6)

    @field_validator("prompt", "expected_result", "starter_code")
    @classmethod
    def no_hidden_grading(cls, value: str | None) -> str | None:
        if value is not None and any(marker in value.lower() for marker in ("hidden_tests", "скрытые тесты", "grader rubric")):
            raise ValueError("internal grading data is not allowed")
        return value

    @field_validator("submission_type")
    @classmethod
    def valid_submission(cls, value: str) -> str:
        if value not in {"text", "python_code"}:
            raise ValueError("unsupported submission type")
        return value


class GeneratedStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int = Field(ge=1, le=MAX_STEPS)
    skill_id: str = Field(min_length=1, max_length=120)
    kind: str
    duration_minutes: int
    lesson: GeneratedLesson
    exercise: GeneratedExercise

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, value: str) -> str:
        if value not in {"learn", "practice", "review"}:
            raise ValueError("unsupported activity kind")
        return value

    @field_validator("duration_minutes")
    @classmethod
    def valid_duration(cls, value: int) -> int:
        if value not in ALLOWED_DURATIONS:
            raise ValueError("duration is not allowed")
        return value


class GeneratedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    steps: list[GeneratedStep] = Field(min_length=1, max_length=MAX_STEPS)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _mastery(row: UserSkill | None) -> float:
    if row is None or row.evidence_count == 0:
        return 0.0
    return max(0.0, min(1.0, 0.45 * row.independent_score + 0.35 * row.knowledge_score + 0.20 * row.practice_score))


def _snapshot(db: Session, user: User) -> tuple[dict, str, CurriculumPlanRevision | None]:
    revision = db.scalar(select(CurriculumPlanRevision).join(
        LearningPlan, CurriculumPlanRevision.plan_id == LearningPlan.id,
    ).where(LearningPlan.user_id == user.id)
        .order_by(CurriculumPlanRevision.version.desc()))
    goal = db.scalar(select(Goal).where(Goal.user_id == user.id))
    mastery = {row.skill_id: row for row in db.scalars(select(UserSkill).where(UserSkill.user_id == user.id))}
    completed = {row.lesson_id for row in db.scalars(select(LessonCompletion).where(LessonCompletion.user_id == user.id))}
    edges = db.scalars(select(SkillEdge).where(SkillEdge.relation == "prerequisite")).all()
    prerequisites: dict[str, list[str]] = {}
    for edge in edges:
        prerequisites.setdefault(edge.to_skill_id, []).append(edge.from_skill_id)
    skills = db.scalars(select(Skill).order_by(Skill.id)).all()
    latest_assessment = db.scalar(select(AssessmentRun).where(
        AssessmentRun.user_id == user.id, AssessmentRun.status == "completed"
    ).order_by(AssessmentRun.completed_at.desc()).limit(1))
    assessment_scores: dict[str, float] = {}
    if latest_assessment is not None:
        grouped: dict[str, list[float]] = {}
        for response in db.scalars(select(AssessmentResponse).where(AssessmentResponse.run_id == latest_assessment.id)):
            grouped.setdefault(response.skill_id, []).append(float(response.is_correct))
        assessment_scores = {skill_id: sum(scores) / len(scores) for skill_id, scores in grouped.items()}
    allowed = []
    for skill in skills:
        required = prerequisites.get(skill.id, [])
        if not all(_mastery(mastery.get(item)) >= 0.75 or item in {
            lesson["skill_id"] for lesson in LESSONS if lesson["id"] in completed
        } for item in required):
            continue
        row = mastery.get(skill.id)
        allowed.append({
            "skill_id": skill.id,
            "name": skill.name,
            "category": skill.category,
            "difficulty": skill.difficulty,
            "importance": skill.importance,
            "mastery": {
                "knowledge": row.knowledge_score if row else 0.0,
                "practice": row.practice_score if row else 0.0,
                "independent": row.independent_score if row else 0.0,
                "retention": row.retention_score if row else 0.0,
                "confidence": row.confidence if row else 0.0,
                "evidence_count": row.evidence_count if row else 0,
            },
            "prerequisites": required,
            "completed": skill.id in {lesson["skill_id"] for lesson in LESSONS if lesson["id"] in completed},
            "assessment_score": assessment_scores.get(skill.id),
        })
    allowed.sort(key=lambda item: (
        item["mastery"]["independent"] + item["mastery"]["knowledge"] + item["mastery"]["practice"],
        -item["importance"], item["skill_id"],
    ))
    allowed = allowed[:40]
    weekly = max(0, goal.weekly_minutes if goal else 0)
    max_total = min(60, weekly)
    snapshot = {
        "snapshot_version": "personalization-input-v1",
        "goal": {"target_role": goal.target_role if goal else "", "weekly_minutes": weekly},
        "assessment_scores": assessment_scores,
        "skills": allowed,
        "authored_lessons": [
            {"lesson_id": lesson["id"], "skill_id": lesson["skill_id"], "minutes": lesson["minutes"]}
            for lesson in LESSONS if lesson["id"] not in completed
        ],
        "limits": {"max_steps": MAX_STEPS, "max_total_minutes": max_total},
    }
    encoded = _json({
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "snapshot": snapshot,
    })
    if len(encoded) > 24000:
        raise ValueError("Personalization context exceeds the configured limit")
    return snapshot, hashlib.sha256(encoded.encode("utf-8")).hexdigest(), revision


def _messages(snapshot: dict) -> list[dict[str, str]]:
    system = (
        "You are an educational curriculum author. Return JSON only, matching the requested schema. "
        "Use only skill_id values from allowed skills. Do not include answers, solutions, rubrics, hidden tests, "
        "grading keys, mastery claims, or prerequisite claims. Never invent a skill. "
        "Create concise learner-facing explanations and an individual exercise; Python code is not executed."
    )
    user = (
        f"Schema version: {SCHEMA_VERSION}. Every exercise must include expected_result, success_criteria, "
        "and evaluation_criteria (the last field is server-only). Never include worked solutions or hidden tests. "
        f"Generate 1-{MAX_STEPS} steps. "
        f"Each duration must be one of {sorted(ALLOWED_DURATIONS)} and total must not exceed "
        f"{snapshot['limits']['max_total_minutes']} minutes. Alternate learn, practice, review when appropriate. "
        "If the budget is below 20, still return the best bounded plan. Input data follows as JSON:\n" + _json(snapshot)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _validate_domain(db: Session, output: GeneratedOutput, snapshot: dict) -> None:
    if output.schema_version != SCHEMA_VERSION:
        raise ValueError("unsupported generation schema")
    allowed = {item["skill_id"]: item for item in snapshot["skills"]}
    positions = [step.position for step in output.steps]
    if positions != list(range(1, len(positions) + 1)):
        raise ValueError("step positions must be consecutive")
    if any(output.steps[index].skill_id == output.steps[index - 1].skill_id
           and output.steps[index].kind != "review" for index in range(1, len(output.steps))):
        raise ValueError("repeated skills must be explicitly marked as review")
    if sum(step.duration_minutes for step in output.steps) > snapshot["limits"]["max_total_minutes"]:
        raise ValueError("generated plan exceeds user time budget")
    for step in output.steps:
        if step.skill_id not in allowed:
            raise ValueError("generated skill is not in the server allowlist")
        if step.exercise.submission_type == "python_code" and not step.exercise.starter_code:
            raise ValueError("python exercise requires starter code")
        if any(len(item) > 160 for item in step.exercise.constraints + step.exercise.evaluation_criteria):
            raise ValueError("exercise constraint is too long")
        if db.get(Skill, step.skill_id) is None:
            raise ValueError("generated skill does not exist")


_USER_LOCKS: dict[str, Lock] = {}
_USER_LOCKS_GUARD = Lock()


def _user_lock(user_id: str) -> Lock:
    with _USER_LOCKS_GUARD:
        return _USER_LOCKS.setdefault(user_id, Lock())


def generate_personalized_plan(db: Session, user: User, *, trigger: str = "manual", force: bool = False) -> dict:
    """Generate outside the evidence transaction; failed calls never replace the last ready result."""
    snapshot, input_hash, source_revision = _snapshot(db, user)
    if source_revision is None:
        raise ValueError("Complete assessment before generating an AI curriculum")
    now = datetime.now(timezone.utc)
    existing = db.scalar(select(AIPlanGeneration).where(
        AIPlanGeneration.user_id == user.id,
        AIPlanGeneration.input_hash == input_hash,
        AIPlanGeneration.model_id == MODEL_ID,
        AIPlanGeneration.status == "ready",
    ).order_by(AIPlanGeneration.generated_at.desc())) if not force else None
    if existing:
        current = db.get(AIPlanCurrent, user.id)
        if current is None:
            db.add(AIPlanCurrent(user_id=user.id, generation_id=existing.id))
        else:
            current.generation_id = existing.id
        db.add(AIUsageLedger(
            user_id=user.id, generation_id=existing.id, operation="curriculum_generation",
            model_id=MODEL_ID, cache_hit=True, input_chars=len(_json(snapshot)),
            output_chars=0, status="cache_hit",
        ))
        db.commit()
        return personalized_response(db, user)
    recent_calls = db.scalar(select(AIUsageLedger.id).where(
        AIUsageLedger.user_id == user.id,
        AIUsageLedger.operation == "curriculum_generation",
        AIUsageLedger.created_at >= now - timedelta(hours=1),
        AIUsageLedger.cache_hit.is_(False),
    ).limit(6))
    if recent_calls is not None:
        raise ai_gateway.GatewayError(429, "AI curriculum budget exceeded; retry later")
    with _user_lock(str(user.id)):
        existing = db.scalar(select(AIPlanGeneration).where(
            AIPlanGeneration.user_id == user.id,
            AIPlanGeneration.input_hash == input_hash,
            AIPlanGeneration.model_id == MODEL_ID,
            AIPlanGeneration.status == "ready",
        ))
        if existing and not force:
            current = db.get(AIPlanCurrent, user.id)
            if current is None:
                db.add(AIPlanCurrent(user_id=user.id, generation_id=existing.id))
            else:
                current.generation_id = existing.id
            db.add(AIUsageLedger(
                user_id=user.id, generation_id=existing.id, operation="curriculum_generation",
                model_id=MODEL_ID, cache_hit=True, input_chars=len(_json(snapshot)),
                output_chars=0, status="cache_hit",
            ))
            db.commit()
            return personalized_response(db, user)
        try:
            config = ai_gateway.configuration(model_override=MODEL_ID)
            prompt_messages = _messages(snapshot)
            raw, usage = ai_gateway.generate_with_usage(config, prompt_messages, max_completion_tokens=2200)
            output_chars = len(raw)
            if len(raw) > MAX_OUTPUT_CHARS:
                raise ValueError("AI curriculum response is too large")
            output = GeneratedOutput.model_validate(json.loads(raw))
            _validate_domain(db, output, snapshot)
        except (ai_gateway.GatewayError, ValueError, ValidationError, json.JSONDecodeError) as exc:
            status = "gateway_error" if isinstance(exc, ai_gateway.GatewayError) else "invalid_output"
            request_chars = sum(len(message["content"]) for message in locals().get("prompt_messages", []))
            db.add(AIUsageLedger(
                user_id=user.id, operation="curriculum_generation", model_id=MODEL_ID,
                cache_hit=False, input_chars=request_chars, output_chars=locals().get("output_chars", 0),
                status=status,
            ))
            db.commit()
            raise
    generation = AIPlanGeneration(
        user_id=user.id, source_revision_id=source_revision.id if source_revision else None,
        model_id=MODEL_ID, prompt_version=PROMPT_VERSION, input_hash=input_hash,
        trigger=trigger, total_minutes=sum(step.duration_minutes for step in output.steps),
    )
    db.add(generation)
    db.flush()
    for step in output.steps:
        db.add(AIPlanStep(
            generation_id=generation.id, position=step.position, skill_id=step.skill_id,
            kind=step.kind, duration_minutes=step.duration_minutes, title=step.lesson.title,
            explanation=step.lesson.explanation, example_code=step.lesson.example_code,
            exercise_prompt=step.exercise.prompt, expected_result=step.exercise.expected_result,
            submission_type=step.exercise.submission_type,
            starter_code=step.exercise.starter_code, constraints=step.exercise.constraints,
            evaluation_criteria=step.exercise.evaluation_criteria,
            success_criteria=step.exercise.success_criteria,
            reason_codes=["ai_generated", "goal_and_mastery_context"],
        ))
    db.add(AIUsageLedger(
        user_id=user.id, generation_id=generation.id, operation="curriculum_generation",
        model_id=MODEL_ID, cache_hit=False,
        input_chars=sum(len(message["content"]) for message in prompt_messages),
        output_chars=len(raw),
        input_tokens=(usage or {}).get("prompt_tokens") if isinstance((usage or {}).get("prompt_tokens"), int) else None,
        output_tokens=(usage or {}).get("completion_tokens") if isinstance((usage or {}).get("completion_tokens"), int) else None,
        status="ready",
    ))
    current = db.get(AIPlanCurrent, user.id)
    if current is None:
        db.add(AIPlanCurrent(user_id=user.id, generation_id=generation.id))
    else:
        current.generation_id = generation.id
    db.commit()
    return personalized_response(db, user)


def personalized_response(db: Session, user: User) -> dict:
    current = db.get(AIPlanCurrent, user.id)
    generation = db.get(AIPlanGeneration, current.generation_id) if current else None
    if generation is None:
        generation = db.scalar(select(AIPlanGeneration).where(
            AIPlanGeneration.user_id == user.id, AIPlanGeneration.status == "ready"
        ).order_by(AIPlanGeneration.generated_at.desc()))
    if generation is None:
        return {"status": "unavailable", "generation_id": None, "steps": []}
    latest_failure = db.scalar(select(AIUsageLedger).where(
        AIUsageLedger.user_id == user.id,
        AIUsageLedger.operation == "curriculum_generation",
        AIUsageLedger.status.in_(("gateway_error", "invalid_output")),
    ).order_by(AIUsageLedger.created_at.desc()).limit(1))
    warning = None
    if latest_failure and latest_failure.created_at > generation.generated_at:
        warning = "Последний запрос AI не удался; показан предыдущий план. Можно повторить генерацию."
    steps = db.scalars(select(AIPlanStep).where(AIPlanStep.generation_id == generation.id).order_by(AIPlanStep.position)).all()
    return {
        "status": "ready", "generation_id": str(generation.id), "generated_at": generation.generated_at,
        "model_id": generation.model_id, "total_minutes": generation.total_minutes, "warning": warning,
        "steps": [{
            "position": step.position, "skill_id": step.skill_id, "kind": step.kind,
            "duration_minutes": step.duration_minutes, "title": step.title,
            "explanation": step.explanation, "example_code": step.example_code,
            "exercise": {"prompt": step.exercise_prompt, "submission_type": step.submission_type,
                         "starter_code": step.starter_code, "constraints": step.constraints,
                         "runner_status": "unavailable" if step.submission_type == "python_code" else None},
            "reason_codes": step.reason_codes,
        } for step in steps],
    }
