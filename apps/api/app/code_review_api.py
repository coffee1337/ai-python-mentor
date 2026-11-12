"""Review a learner's last submission against the weighted rubric.

The endpoint is deliberately narrow: it reviews code the learner already submitted,
it never invents a submission, and it refuses a model answer that does not match the
schema instead of showing a made-up score.
"""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ai_gateway, rubric, secret_scan
from app.auth import csrf_protected, current_auth
from app.db.models import CodeReview, CodingAttempt, User
from app.db.session import get_db
from app.learning import accessible_lesson, require_onboarding

router = APIRouter(prefix="/learning", tags=["code-review"])


@router.get("/rubric")
def rubric_definition() -> dict:
    """Weights for every level, so the UI shows what is actually graded."""
    return {
        "criteria": [{"id": key, "title": rubric.TITLES[key]} for key in rubric.CRITERIA],
        "levels": {level: weights for level, weights in rubric.LEVEL_WEIGHTS.items()},
        "pass_threshold": rubric.PASS_THRESHOLD,
        "max_points_per_criterion": rubric.MAX_POINTS,
    }


@router.post("/exercises/{exercise_id}/review", status_code=201)
def review(
    exercise_id: str,
    auth: tuple[User, object] = Depends(csrf_protected),
    db: Session = Depends(get_db),
) -> dict:
    user, _ = auth
    require_onboarding(user)
    if not exercise_id.endswith("-code"):
        accessible_lesson(exercise_id, db, user)
    attempt = db.scalar(
        select(CodingAttempt)
        .where(CodingAttempt.user_id == user.id, CodingAttempt.exercise_id == exercise_id)
        .order_by(CodingAttempt.created_at.desc())
    )
    if attempt is None:
        raise HTTPException(404, "Сначала отправьте решение: ревью оценивает ваш код.")
    level = user.profile.experience_level if user.profile is not None else None
    try:
        config = ai_gateway.configuration(task="code_review")
    except ai_gateway.GatewayError:
        raise HTTPException(503, "AI-ревью сейчас недоступно; код и тесты работают.") from None
    try:
        # Defence in depth: even a submission stored before scanning existed is
        # redacted before it can reach a provider.
        safe_source = secret_scan.redact(attempt.source_code)
        answer = ai_gateway.generate(
            config, rubric.messages(safe_source, level=level, exercise_title=exercise_id)
        )
    except ai_gateway.GatewayError:
        raise HTTPException(503, "AI-ревью сейчас недоступно; попробуйте позже.") from None
    try:
        result = rubric.review(answer, level)
    except rubric.InvalidReview:
        # No partial credit and no guessed numbers: the learner is told to retry.
        raise HTTPException(502, "Ревью не прошло проверку формата; попробуйте ещё раз.") from None
    row = CodeReview(
        id=uuid4(),
        user_id=user.id,
        exercise_id=exercise_id,
        attempt_id=attempt.id,
        level=result.level,
        score=result.score,
        grades=result.grades,
        notes=result.notes,
        model=config.model,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    return {"id": str(row.id), "exercise_id": exercise_id, "model": config.model, **result.as_dict()}


@router.get("/exercises/{exercise_id}/reviews")
def history(exercise_id: str, auth: tuple[User, object] = Depends(current_auth),
            db: Session = Depends(get_db)) -> list[dict]:
    user, _ = auth
    rows = db.scalars(
        select(CodeReview)
        .where(CodeReview.user_id == user.id, CodeReview.exercise_id == exercise_id)
        .order_by(CodeReview.created_at.desc())
        .limit(20)
    ).all()
    return [
        {
            "id": str(row.id),
            "score": row.score,
            "level": row.level,
            "grades": row.grades,
            "created_at": row.created_at,
        }
        for row in rows
    ]
