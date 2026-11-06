from typing import Literal

from pydantic import BaseModel, Field


class ActionPayload(BaseModel):
    id: str
    name: str
    duration_minutes: int
    intensity: Literal["normal", "gentle"]
    steps: list[str]
    caution: str = ""


class HeartbeatRequest(BaseModel):
    sitting_minutes: int = Field(ge=0, le=1440)
    threshold_minutes: int = Field(default=45, ge=30, le=60)


class HeartbeatResponse(BaseModel):
    triggered: bool
    reason: Literal["below_threshold", "cooldown", "triggered", "no_action_available"]
    state: str
    sitting_minutes: int
    threshold_minutes: int
    next_check_minutes: int
    action: ActionPayload | None = None