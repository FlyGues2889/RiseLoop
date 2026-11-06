from typing import Literal

from pydantic import BaseModel, Field

BodyPart = Literal["neck", "shoulder", "upper_back", "low_back", "hip", "core"]


class AssessmentRequest(BaseModel):
    body_parts: list[BodyPart] = Field(min_length=1)
    sedentary_minutes: int = Field(ge=0, le=1440)
    available_minutes: int = Field(ge=1, le=120)
    pain_score: int = Field(ge=0, le=10)
    acute_discomfort: bool = False


class TwoWeekPlan(BaseModel):
    week1_goal: str
    week2_goal: str
    push_threshold_minutes: int
    min_completions_per_week: int


class AssessmentResponse(BaseModel):
    assessment_id: str
    initial_state: str
    state_name: str
    risk_level: Literal["low", "medium", "high"]
    duration_range: str
    intensity: Literal["normal", "gentle"]
    plan: TwoWeekPlan
    stop_exercise: bool = False
    disclaimer: str


class RegisterRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int