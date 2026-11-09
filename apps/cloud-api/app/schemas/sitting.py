from typing import Literal

from pydantic import BaseModel, Field


class ActionPayload(BaseModel):
    id: str
    name: str
    duration_minutes: int
    intensity: Literal["normal", "gentle"]
    body_parts: list[str] = Field(default_factory=list)
    steps: list[str]
    caution: str = ""
    match_reason: str = ""


class HeartbeatRequest(BaseModel):
    sitting_minutes: int = Field(ge=0, le=1440)
    threshold_minutes: int = Field(default=45, ge=30, le=60)
    # 演示/手动触发时跳过 10 分钟冷却，正常心跳保持 False
    force: bool = False


class HeartbeatResponse(BaseModel):
    triggered: bool
    reason: Literal["below_threshold", "cooldown", "triggered", "no_action_available"]
    state: str
    sitting_minutes: int
    threshold_minutes: int
    next_check_minutes: int
    action: ActionPayload | None = None
    actions: list[ActionPayload] = Field(default_factory=list)