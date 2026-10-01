from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuthSession, Goal, Profile, User
from app.db.session import get_db
from app.schemas import AuthResponse, LoginRequest, OnboardingRequest, OnboardingResponse, ProfilePatch, RegisterRequest, UserResponse
from app.security import hash_password, new_token, token_digest, verify_password

SESSION_COOKIE = "mentor_session"
CSRF_COOKIE = "mentor_csrf"
SESSION_TTL = timedelta(days=30)
AUTH_RATE_LIMIT = 20
AUTH_RATE_WINDOW_SECONDS = 60.0
_attempts: dict[str, list[float]] = {}
_attempts_lock = Lock()
router = APIRouter(tags=["auth"])


def _cookie_secure() -> bool:
    default = "true" if os.getenv("APP_ENV", "development").casefold() == "production" else "false"
    return os.getenv("COOKIE_SECURE", default).casefold() == "true"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rate_limit(request: Request) -> None:
    address = request.client.host if request.client else "unknown"
    now = monotonic()
    with _attempts_lock:
        recent = [stamp for stamp in _attempts.get(address, []) if now - stamp < AUTH_RATE_WINDOW_SECONDS]
        if len(recent) >= AUTH_RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Too many authentication attempts")
        _attempts[address] = recent + [now]


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
    return UserResponse.model_validate(user)


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
    return _find_session(request, db)


def csrf_protected(request: Request, auth: tuple[User, AuthSession] = Depends(current_auth), x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> tuple[User, AuthSession]:
    _, session = auth
    cookie_token = request.cookies.get(CSRF_COOKIE)
    if not cookie_token or not x_csrf_token or cookie_token != x_csrf_token or token_digest(x_csrf_token) != session.csrf_token_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    return auth


@router.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    _rate_limit(request)
    if db.scalar(select(User).where(User.email == payload.email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to create account")
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    session_token, csrf_token = _create_session(db, user)
    db.commit()
    db.refresh(user)
    _set_auth_cookies(response, session_token, csrf_token)
    return AuthResponse(user=_user_response(user), onboarding_required=True)


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    _rate_limit(request)
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
