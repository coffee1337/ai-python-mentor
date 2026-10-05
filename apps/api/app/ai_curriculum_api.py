from fastapi import APIRouter, Depends, HTTPException

from app.auth import csrf_protected, current_auth
from app.ai_curriculum import generate_personalized_plan, personalized_response
from app.db.models import AuthSession, User
from app.db.session import get_db
from app.learning import require_onboarding

router = APIRouter(prefix="/learning", tags=["ai-curriculum"])


@router.get("/personalized-plan")
def get_personalized_plan(auth: tuple[User, AuthSession] = Depends(current_auth), db=Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    return personalized_response(db, user)


@router.post("/personalized-plan/generate")
def generate_plan(auth: tuple[User, AuthSession] = Depends(csrf_protected), db=Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    try:
        return generate_personalized_plan(db, user, trigger="manual")
    except Exception as exc:
        if hasattr(exc, "status"):
            raise HTTPException(int(exc.status), "AI curriculum generation failed") from None
        raise HTTPException(502, "AI curriculum generation failed; the previous plan was preserved") from None
