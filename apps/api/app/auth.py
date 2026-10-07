from __future__ import annotations

import os
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AuthSession, Goal, Profile, User
from app.db.session import get_db
from app.schemas import AuthResponse, LoginRequest, OnboardingRequest, OnboardingResponse, ProfilePatch, RegisterRequest, UserResponse
from app.security import hash_password, new_token, token_digest, verify_password
from app.account_services import throttle

SESSION_COOKIE = "mentor_session"
CSRF_COOKIE = "mentor_csrf"
SESSION_TTL = timedelta(days=30)
AUTH_RATE_LIMIT = 20
AUTH_RATE_WINDOW_SECONDS = 60.0
_attempts: dict[str, list[float]] = {}
router = APIRouter(tags=["auth"])


def _cookie_secure() -> bool:
    if os.getenv("APP_ENV", "development").casefold() == "production":
        return True
    return os.getenv("COOKIE_SECURE", "false").casefold() == "true"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rate_limit(request: Request, db: Session, email: str) -> None:
    address = request.client.host if request.client else "unknown"
    throttle(db, scope="auth_ip", subject=address, limit=AUTH_RATE_LIMIT)
    throttle(db, scope="auth_account", subject=email, limit=AUTH_RATE_LIMIT)


def _set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    secure = _cookie_secure()
    response.set_cookie(SESSION_COOKIE, session_token, max_age=int(SESSION_TTL.total_seconds()), httponly=True, secure=secure, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf_token, max_age=int(SESSION_TTL.total_seconds()), httponly=False, secure=secure, samesite="lax", path="/")


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _create_session(db: Session, user: User) -> tuple[str, str]:
    session_token, csrf_token = new_token(), new_token()
    db.add(AuthSession(user_id=user.id, token_hash=token_digest(session_token), csrf_token_hash=token_digest(csrf_token), expires_at=_now() + SESSION_TTL))
    return session_token, csrf_token


def _user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user).model_copy(update={"account_scope": account_scope(user)})


def account_scope(user: User) -> str:
    """Opaque account precondition, never a credential or an owner selector.

    An old tab retains this value when another tab changes the shared cookies.
    It can then fail closed before copying private work to the new account.
    Password rotation invalidates the old precondition as well.
    """
    return hmac.new(user.password_hash.encode("utf-8"),
        ("mentor-workspace-scope-v1\0" + str(user.id)).encode("utf-8"), hashlib.sha256).hexdigest()


def _onboarding_required(user: User) -> bool:
    return user.profile is None or not user.profile.onboarding_completed


def _find_session(request: Request, db: Session) -> tuple[User, AuthSession]:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(raw_token)))
    now = _now()
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session is not None and session.expires_at.tzinfo is None else (session.expires_at if session is not None else None)
    if session is None or session.revoked_at is not None or expires_at <= now or session.user is None or not session.user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    session.last_seen_at = now
    return session.user, session


def current_auth(request: Request, db: Session = Depends(get_db)) -> tuple[User, AuthSession]:
    auth = _find_session(request, db)
    # Session inventory must reflect successful GETs as well as write endpoints.
    db.commit()
    return auth


def csrf_protected(request: Request, auth: tuple[User, AuthSession] = Depends(current_auth),
                   x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
                   x_account_scope: str | None = Header(default=None, alias="X-Account-Scope", max_length=64)) -> tuple[User, AuthSession]:
    _, session = auth
    cookie_token = request.cookies.get(CSRF_COOKIE)
    if not cookie_token or not x_csrf_token or cookie_token != x_csrf_token or token_digest(x_csrf_token) != session.csrf_token_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    if x_account_scope is not None:
        _check_account_scope(auth, x_account_scope)
    return auth


def _check_account_scope(auth: tuple[User, AuthSession], expected: str | None) -> tuple[User, AuthSession]:
    if (expected is None or len(expected) != 64 or any(part not in "0123456789abcdef" for part in expected)
            or not hmac.compare_digest(expected, account_scope(auth[0]))):
        raise HTTPException(409, {"code": "account_changed", "message": "Account changed; reload before continuing"},
                            headers={"Cache-Control": "no-store"})
    return auth


def account_scoped_auth(auth: tuple[User, AuthSession] = Depends(current_auth),
                        expected: str | None = Header(default=None, alias="X-Account-Scope", max_length=64)):
    return _check_account_scope(auth, expected)


def account_scoped_csrf(auth: tuple[User, AuthSession] = Depends(csrf_protected),
                        expected: str | None = Header(default=None, alias="X-Account-Scope", max_length=64)):
    return _check_account_scope(auth, expected)


@router.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    _rate_limit(request, db, payload.email)
    if db.scalar(select(User).where(User.email == payload.email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to create account")
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to create account") from None
    session_token, csrf_token = _create_session(db, user)
    db.commit()
    db.refresh(user)
    _set_auth_cookies(response, session_token, csrf_token)
    return AuthResponse(user=_user_response(user), onboarding_required=True)


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    _rate_limit(request, db, payload.email)
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    existing_token = request.cookies.get(SESSION_COOKIE)
    if existing_token:
        existing_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(existing_token)))
        if existing_session is not None and existing_session.revoked_at is None:
            existing_session.revoked_at = _now()
    session_token, csrf_token = _create_session(db, user)
    db.commit()
    db.refresh(user)
    _set_auth_cookies(response, session_token, csrf_token)
    return AuthResponse(user=_user_response(user), onboarding_required=_onboarding_required(user))


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)) -> None:
    _, session = auth
    session.revoked_at = _now()
    db.commit()
    _clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
def me(auth: tuple[User, AuthSession] = Depends(current_auth)) -> UserResponse:
    user, _ = auth
    return _user_response(user)


@router.patch("/me/profile", response_model=UserResponse)
def update_profile(payload: ProfilePatch, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)) -> UserResponse:
    user, _ = auth
    profile = user.profile or Profile(user_id=user.id)
    if user.profile is None:
        db.add(profile)
    if payload.display_name is not None:
        profile.display_name = payload.display_name.strip()
    if payload.experience_level is not None:
        profile.experience_level = payload.experience_level.strip()
    db.commit()
    db.refresh(user)
    return _user_response(user)


@router.get("/onboarding", response_model=OnboardingResponse)
def get_onboarding(auth: tuple[User, AuthSession] = Depends(current_auth)) -> OnboardingResponse:
    user, _ = auth
    return OnboardingResponse(completed=not _onboarding_required(user), profile=user.profile, goal=user.goal)


@router.post("/onboarding", response_model=OnboardingResponse)
def complete_onboarding(payload: OnboardingRequest, auth: tuple[User, AuthSession] = Depends(csrf_protected), db: Session = Depends(get_db)) -> OnboardingResponse:
    user, _ = auth
    profile = user.profile or Profile(user_id=user.id)
    if user.profile is None:
        db.add(profile)
    profile.display_name = payload.display_name.strip() if payload.display_name else None
    profile.experience_level = payload.experience_level.strip()
    profile.onboarding_completed = True
    goal = user.goal or Goal(user_id=user.id, target_role=payload.target_role.strip())
    if user.goal is None:
        db.add(goal)
    goal.target_role = payload.target_role.strip()
    goal.weekly_minutes = payload.weekly_minutes
    goal.motivation = payload.motivation.strip() if payload.motivation else None
    db.commit()
    db.refresh(user)
    return OnboardingResponse(completed=True, profile=user.profile, goal=user.goal)
