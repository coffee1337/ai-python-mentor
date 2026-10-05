from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.auth import csrf_protected, current_auth
from app.db.models import AuthSession, User
from app.db.session import get_db
from app.curriculum import build_curriculum, curriculum_response
from app.learning import require_onboarding

router = APIRouter(prefix="/learning", tags=["curriculum"])


@router.get("/curriculum")
def get_curriculum(auth: tuple[User, AuthSession] = Depends(current_auth), db=Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    return curriculum_response(db, user)


@router.post("/curriculum/refresh")
def refresh_curriculum(auth: tuple[User, AuthSession] = Depends(csrf_protected), db=Depends(get_db)):
    user, _ = auth
    require_onboarding(user)
    revision = build_curriculum(db, user, reason="manual_refresh")
    if revision is None:
        raise HTTPException(409, "Complete assessment before building a curriculum")
    db.commit()
    return curriculum_response(db, user)
