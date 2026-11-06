from typing import Literal

from pydantic import BaseModel

from ..cloud.base import ServiceStatus


class LiveResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    dependencies: list[ServiceStatus]


class DependencyResponse(BaseModel):
    dependencies: list[ServiceStatus]