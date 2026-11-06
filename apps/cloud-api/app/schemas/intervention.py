from typing import Literal

from intervention_engine import Completion, Feeling, Obstacle, RedFlag
from pydantic import BaseModel, Field

from ..schemas.sitting import ActionPayload


class FeedbackRequest(BaseModel):
    action_id: str
    completion: Completion
    feeling: Feeling = Feeling.SAME
    pain_score: int = Field(default=0, ge=0, le=10)
    obstacle: Obstacle | None = None
    next_day_worse: bool = False
    red_flags: list[RedFlag] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    from_state: str
    to_state: str
    transition_type: str
    reason: str
    duration_range: str
    intensity: Literal["normal", "gentle"]
    stop_exercise: bool = False
    medical_advice: bool = False
    next_action: ActionPayload | None = None
    disclaimer: str