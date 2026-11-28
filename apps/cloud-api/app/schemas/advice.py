from typing import Any, Literal

from pydantic import BaseModel, Field

Surface = Literal["weekly", "posture", "transition", "timer"]


class AdviceRequest(BaseModel):
    surface: Surface
    state: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    # 模型不可用时原样返回，前端不用再写一份回落文案
    fallback: str = ""


class AdviceResponse(BaseModel):
    text: str
    source: Literal["model", "template"] = "template"
