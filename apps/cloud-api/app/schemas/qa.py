from pydantic import BaseModel, Field


class QaRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    state: str | None = None
    body_parts: list[str] = Field(default_factory=list)


class QaResponse(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    state_hint: str | None = None
    escalated_to_medical: bool = False
    disclaimer: str