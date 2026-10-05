from fastapi import APIRouter, Depends
from app.auth import current_auth
from app.db.models import AuthSession, User
from app.db.session import get_db
from app.learning import require_onboarding
from app.learning_plan import plan_response
from app.curriculum import curriculum_response
from app.ai_curriculum import personalized_response

router=APIRouter(prefix="/learning", tags=["learning-plan"])
@router.get("/plan")
def get_plan(auth:tuple[User,AuthSession]=Depends(current_auth), db=Depends(get_db)):
    user,_=auth; require_onboarding(user)
    return {
        **plan_response(db, user).model_dump(),
        "curriculum": curriculum_response(db, user),
        "personalized_plan": personalized_response(db, user),
    }
