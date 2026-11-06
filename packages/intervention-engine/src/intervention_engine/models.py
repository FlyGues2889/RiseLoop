from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class State(StrEnum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"


class TransitionType(StrEnum):
    UPGRADE = "upgrade"
    ROLLBACK = "rollback"
    DEGRADE = "degrade"
    SHORT_CIRCUIT = "short_circuit"
    HOLD = "hold"


class RedFlag(StrEnum):
    RADIATING_PAIN = "radiating_pain"
    NUMBNESS_WORSE = "numbness_worse"
    DIZZINESS = "dizziness"
    LEG_WEAKNESS = "leg_weakness"
    COTTON_WOOL_GAIT = "cotton_wool_gait"
    BOWEL_BLADDER = "bowel_bladder"
    PERINEAL_NUMBNESS = "perineal_numbness"
    POST_TRAUMA_SEVERE_PAIN = "post_trauma_severe_pain"


class Completion(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class Feeling(StrEnum):
    BETTER = "better"
    SAME = "same"
    WORSE = "worse"


class Obstacle(StrEnum):
    BUSY = "busy"
    TOO_HARD = "too_hard"
    NO_SPACE = "no_space"
    FORGOT = "forgot"


class Feedback(BaseModel):
    model_config = ConfigDict(frozen=True)

    completion: Completion
    feeling: Feeling = Feeling.SAME
    pain_score: int = Field(default=0, ge=0, le=10)
    next_day_worse: bool = False
    red_flags: tuple[RedFlag, ...] = ()
    obstacle: Obstacle | None = None


class StateCounters(BaseModel):
    model_config = ConfigDict(frozen=True)

    completed_streak: int = Field(default=0, ge=0)
    skipped_streak: int = Field(default=0, ge=0)
    worse_streak: int = Field(default=0, ge=0)
    s0_completed: int = Field(default=0, ge=0)


class EngineInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: State
    feedback: Feedback
    counters: StateCounters = Field(default_factory=StateCounters)


class EngineOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_state: State
    to_state: State
    transition_type: TransitionType
    reason: str
    duration_minutes: tuple[int, int]
    intensity: Literal["normal", "gentle"]
    stop_exercise: bool = False
    medical_advice: bool = False
    counters: StateCounters