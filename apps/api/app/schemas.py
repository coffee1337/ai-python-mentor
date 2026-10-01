from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    profile: ProfileResponse | None = None
    goal: GoalResponse | None = None


class AuthResponse(BaseModel):
    user: UserResponse
    onboarding_required: bool


class OnboardingResponse(BaseModel):
    completed: bool
    profile: ProfileResponse | None = None
    goal: GoalResponse | None = None
