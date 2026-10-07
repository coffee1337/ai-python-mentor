from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.security import normalize_email


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = normalize_email(value)
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Enter a valid email address")
        return value


class LoginRequest(RegisterRequest):
    pass


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    experience_level: str | None = Field(default=None, min_length=1, max_length=32)


class OnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    experience_level: str = Field(min_length=1, max_length=32)
    target_role: str = Field(min_length=2, max_length=120)
    weekly_minutes: int = Field(default=180, ge=15, le=1200)
    motivation: str | None = Field(default=None, max_length=2000)


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    display_name: str | None = None
    experience_level: str | None = None
    onboarding_completed: bool = False


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_role: str
    weekly_minutes: int
    motivation: str | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    email_verified: bool
    account_scope: str | None = None
    profile: ProfileResponse | None = None
    goal: GoalResponse | None = None


class AuthResponse(BaseModel):
    user: UserResponse
    onboarding_required: bool


class OnboardingResponse(BaseModel):
    completed: bool
    profile: ProfileResponse | None = None
    goal: GoalResponse | None = None


class ReviewTodayQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=4000)
    choices: list[str] = Field(min_length=1, max_length=8)


class ReviewTodayItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_token: str = Field(min_length=32, max_length=200)
    skill_id: str = Field(min_length=1, max_length=120)
    scheduled_for: date
    overdue_days: int = Field(ge=0, le=36500)
    questions: list[ReviewTodayQuestion] = Field(min_length=1, max_length=20)


class ReviewTodayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    items: list[ReviewTodayItem] = Field(max_length=100)


class ReviewTodayCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_token: str = Field(min_length=32, max_length=200)
    answers: dict[StrictStr, StrictStr] = Field(min_length=1, max_length=20)

    @field_validator("answers")
    @classmethod
    def valid_answers(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not 1 <= len(key) <= 100 for key in value):
            raise ValueError("Answers are invalid")
        if any(not 1 <= len(answer) <= 200 for answer in value.values()):
            raise ValueError("Answers are invalid")
        return value


class ReviewTodayCompleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["recorded", "replayed"]
    outcome: Literal["correct", "partial", "incorrect"]
    schedule_applied: bool
    same_day: bool
    next_review_at: datetime | None = None
