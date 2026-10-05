"""Server-side AI curriculum generation with strict domain validation."""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app import ai_gateway
from app.db.models import (
    AIPlanCurrent, AIPlanGeneration, AIPlanStep, AIUsageLedger, CurriculumPlanRevision,
    AssessmentResponse, AssessmentRun, Goal, LearningPlan, LessonCompletion,
    Skill, SkillEdge, User, UserSkill,
)
from app.learning_content import LESSONS
from app.prerequisites import prerequisite_state
from app.ai_admission import reserve_ai_call, finish_ai_call
from app.db.domain_models import AIGenerationInput

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
    authored_exercise_id: str | None = Field(default=None, max_length=80)
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
    readiness = prerequisite_state(db, user.id)
    completed = set(readiness.completed_lesson_ids)
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
    from app.curriculum import selected_vacancy
    vacancy, vacancy_skills = selected_vacancy(db, user.id)
    for skill in skills:
        required = prerequisites.get(skill.id, [])
        if not readiness.is_skill_ready(skill.id):
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
            "completed": skill.id in readiness.completed_primary_skills,
            "assessment_score": assessment_scores.get(skill.id),
        })
    allowed.sort(key=lambda item: (
        item["skill_id"] not in vacancy_skills,
        item["mastery"]["independent"] + item["mastery"]["knowledge"] + item["mastery"]["practice"],
        -item["importance"], item["skill_id"],
    ))
    allowed = allowed[:40]
    weekly = max(0, goal.weekly_minutes if goal else 0)
    max_total = min(60, weekly)
    from app.db.models import UserMistake, MisconceptionVersion
    mistakes = db.execute(select(UserMistake, MisconceptionVersion).join(
        MisconceptionVersion, UserMistake.misconception_code == MisconceptionVersion.misconception_code,
    ).where(UserMistake.user_id == user.id, MisconceptionVersion.version == 1)
        .order_by(UserMistake.last_seen_at.desc()).limit(6)).all()
    from app.practice_catalog import trusted_exercises_for_skill
    for item in allowed:
        item["trusted_python_exercises"] = trusted_exercises_for_skill(item["skill_id"])
    snapshot = {
        "snapshot_version": "personalization-input-v1",
        "goal": {"target_role": goal.target_role if goal else "", "weekly_minutes": weekly},
        "selected_vacancy": vacancy,
        "assessment_scores": assessment_scores,
        "mistake_signals": [{"skill_id": item.skill_id, "count": item.occurrence_count,
                             "description": concept.error_text[:240], "remediation": concept.remediation_text[:400]} for item, concept in mistakes],
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
        "Create concise learner-facing explanations and an individual exercise. Python exercises must set authored_exercise_id from that skill trusted_python_exercises; otherwise use text. Treat mistake_signals as possible authored learning signals, never as a diagnosis."
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
        if step.exercise.submission_type == "python_code":
            from app.practice_catalog import trusted_exercise
            if not trusted_exercise(step.skill_id, step.exercise.authored_exercise_id):
                raise ValueError("Python exercises must use the trusted server catalog")
        if db.get(Skill, step.skill_id) is None:
            raise ValueError("generated skill does not exist")


def _activate_cached(db: Session, user: User, existing: AIPlanGeneration, snapshot: dict) -> dict:
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


def _cached_generation(db: Session, user_id, input_hash: str):
    return db.scalar(select(AIPlanGeneration).where(
        AIPlanGeneration.user_id == user_id,
        or_(AIPlanGeneration.input_hash == input_hash,
            AIPlanGeneration.id.in_(select(AIGenerationInput.generation_id).where(AIGenerationInput.input_hash == input_hash))),
        AIPlanGeneration.model_id == MODEL_ID, AIPlanGeneration.status == "ready",
    ).order_by(AIPlanGeneration.generated_at.desc(), AIPlanGeneration.id.desc()).limit(1))


def generate_personalized_plan(db: Session, user: User, *, trigger: str = "manual", force: bool = False) -> dict:
    """Durable admission and fenced publication; no lock spans a gateway call."""
    snapshot, input_hash, source_revision = _snapshot(db, user)
    if source_revision is None:
        raise ValueError("Complete assessment before generating an AI curriculum")
    user_id, source_revision_id = user.id, source_revision.id
    existing = _cached_generation(db, user_id, input_hash)
    if existing and not force:
        return _activate_cached(db, user, existing, snapshot)
    prompt_messages = _messages(snapshot)
    request_chars = sum(len(message["content"]) for message in prompt_messages)
    reservation = reserve_ai_call(
        db, user_id, "curriculum_generation", f"{MODEL_ID}:{input_hash}",
        limit=6, window_seconds=3600, input_chars=request_chars,
    )
    # A prior worker may have published immediately before this reservation.
    existing = _cached_generation(db, user_id, input_hash)
    if existing and not force:
        finish_ai_call(db, reservation, status="ready")
        return _activate_cached(db, user, existing, snapshot)
    db.commit()  # Release every read transaction before external network I/O.
    output_chars, usage = 0, None
    try:
        config = ai_gateway.configuration(model_override=MODEL_ID)
        raw, usage = ai_gateway.generate_with_usage(config, prompt_messages, max_completion_tokens=2200)
        output_chars = len(raw)
        if len(raw) > MAX_OUTPUT_CHARS:
            raise ValueError("AI curriculum response is too large")
        output = GeneratedOutput.model_validate(json.loads(raw))
        _validate_domain(db, output, snapshot)
    except (ai_gateway.GatewayError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        status = "gateway_error" if isinstance(exc, ai_gateway.GatewayError) else "invalid_output"
        finish_ai_call(db, reservation, status=status, usage=usage)
        db.add(AIUsageLedger(
            user_id=user_id, operation="curriculum_generation", model_id=MODEL_ID,
            cache_hit=False, input_chars=request_chars, output_chars=output_chars,
            status=status,
        ))
        db.commit()
        raise
    finish_ai_call(db, reservation, status="ready", usage=usage, model_id=MODEL_ID)
    # Existing immutable generations remain available. Forced regeneration has
    # a distinct cache identity rather than violating the published-key UNIQUE.
    stored_hash = input_hash
    if force and existing:
        from uuid import uuid4
        stored_hash = hashlib.sha256(f"{input_hash}:{uuid4()}".encode()).hexdigest()
    generation = AIPlanGeneration(
        user_id=user_id, source_revision_id=source_revision_id,
        model_id=MODEL_ID, prompt_version=PROMPT_VERSION, input_hash=stored_hash,
        trigger=trigger, total_minutes=sum(step.duration_minutes for step in output.steps),
        generated_at=datetime.now(timezone.utc),
    )
    db.add(generation)
    db.flush()
    db.add(AIGenerationInput(generation_id=generation.id, input_hash=input_hash))
    for step in output.steps:
        stored_step = AIPlanStep(
            generation_id=generation.id, position=step.position, skill_id=step.skill_id,
            kind=step.kind, duration_minutes=step.duration_minutes, title=step.lesson.title,
            explanation=step.lesson.explanation, example_code=step.lesson.example_code,
            exercise_prompt=step.exercise.prompt, expected_result=step.exercise.expected_result,
            submission_type=step.exercise.submission_type,
            starter_code=step.exercise.starter_code, constraints=step.exercise.constraints,
            evaluation_criteria=step.exercise.evaluation_criteria,
            success_criteria=step.exercise.success_criteria,
            reason_codes=["ai_generated", "goal_and_mastery_context"] +
                         (["authored_mistake_remediation"] if snapshot["mistake_signals"] else []),
        )
        db.add(stored_step)
        db.flush()
        if step.exercise.submission_type == "python_code":
            from app.practice_catalog import bind_generated_step
            bind_generated_step(db, stored_step, step.exercise.authored_exercise_id)
    db.add(AIUsageLedger(
        user_id=user_id, generation_id=generation.id, operation="curriculum_generation",
        model_id=MODEL_ID, cache_hit=False, input_chars=request_chars,
        output_chars=output_chars,
        input_tokens=usage.get("prompt_tokens") if isinstance(usage, dict) and type(usage.get("prompt_tokens")) is int else None,
        output_tokens=usage.get("completion_tokens") if isinstance(usage, dict) and type(usage.get("completion_tokens")) is int else None,
        status="ready",
    ))
    current = db.get(AIPlanCurrent, user_id)
    if current is None:
        db.add(AIPlanCurrent(user_id=user_id, generation_id=generation.id))
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
    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    revision = db.scalar(select(CurriculumPlanRevision).join(LearningPlan, CurriculumPlanRevision.plan_id == LearningPlan.id).where(
        LearningPlan.user_id == user.id).order_by(CurriculumPlanRevision.version.desc()).limit(1))
    is_stale = revision is not None and generation.source_revision_id != revision.id
    try:
        _, current_hash, _ = _snapshot(db, user)
        recorded_input = db.get(AIGenerationInput, generation.id)
        is_stale = is_stale or current_hash != (recorded_input.input_hash if recorded_input else generation.input_hash)
    except ValueError:
        is_stale = True
    if latest_failure and utc(latest_failure.created_at) > utc(generation.generated_at):
        warning = "Последний запрос AI не удался; показан предыдущий план. Можно повторить генерацию."
    elif is_stale:
        warning = "Прогресс изменился; обновите индивидуальный план."
    steps = db.scalars(select(AIPlanStep).where(AIPlanStep.generation_id == generation.id).order_by(AIPlanStep.position)).all()
    return {
        "status": "ready", "generation_id": str(generation.id), "generated_at": generation.generated_at,
        "model_id": generation.model_id, "total_minutes": generation.total_minutes, "warning": warning, "is_stale": is_stale,
        "steps": [{
            "step_id": str(step.id), "position": step.position, "skill_id": step.skill_id, "kind": step.kind,
            "duration_minutes": step.duration_minutes, "title": step.title,
            "explanation": step.explanation, "example_code": step.example_code,
            "exercise": {"prompt": step.exercise_prompt, "submission_type": step.submission_type,
                         "starter_code": step.starter_code, "constraints": step.constraints,
                         "expected_result": step.expected_result, "success_criteria": step.success_criteria,
                         "runner_status": "unavailable" if step.submission_type == "python_code" else None},
            "reason_codes": step.reason_codes,
        } for step in steps],
    }
