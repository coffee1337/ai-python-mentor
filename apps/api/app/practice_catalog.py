"""Generated plans may select an authored coding task, never invent its grader."""
from sqlalchemy import select

from app.db.models import AIPlanGeneration, User
from app.db.product_models import GeneratedPracticeBinding


def trusted_exercises_for_skill(skill_id: str) -> list[str]:
    from app.runner_exercise_content import trusted_exercises_for_skill as lookup
    return lookup(skill_id)


def trusted_exercise(skill_id: str, exercise_id: str) -> bool:
    from app.runner_exercise_content import trusted_exercise as check
    return check(skill_id, exercise_id)


def bind_generated_step(db, step, authored_exercise_id: str) -> GeneratedPracticeBinding:
    from app.coding_exercises import resolve_coding_exercise
    generation = db.get(AIPlanGeneration, step.generation_id)
    user = db.get(User, generation.user_id) if generation is not None else None
    if user is None or not trusted_exercise(step.skill_id, authored_exercise_id):
        raise ValueError("Generated coding exercise is outside the authored catalog")
    item, version = resolve_coding_exercise(db, user, authored_exercise_id)
    if item["skill_id"] != step.skill_id:
        raise ValueError("Generated coding exercise skill does not match")
    # A generated explanation cannot change the trusted assignment or entrypoint.
    step.exercise_prompt = item["prompt"]
    step.starter_code = item["starter_code"]
    binding = GeneratedPracticeBinding(step_id=step.id, exercise_id=authored_exercise_id, exercise_version_id=version.id)
    db.add(binding)
    db.flush()
    return binding
