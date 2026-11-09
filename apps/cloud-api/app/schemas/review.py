from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InterventionStats(BaseModel):
    total: int = 0
    completed: int = 0
    completion_rate: float = 0.0


class PainStats(BaseModel):
    average: float | None = None
    latest: int | None = None
    trend: Literal["improving", "stable", "worsening", "unknown"] = "unknown"


class PostureStats(BaseModel):
    samples: int = 0
    dominant: str | None = None
    high_risk_ratio: float = 0.0


class ObstacleCount(BaseModel):
    obstacle: str
    count: int


class WeeklyReview(BaseModel):
    days: int
    generated_at: datetime
    current_state: str | None = None
    interventions: InterventionStats
    pain: PainStats
    transitions: dict[str, int] = Field(default_factory=dict)
    top_obstacles: list[ObstacleCount] = Field(default_factory=list)
    safety_events: int = 0
    sitting_events: int = 0
    posture: PostureStats = Field(default_factory=PostureStats)
    highlights: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    disclaimer: str