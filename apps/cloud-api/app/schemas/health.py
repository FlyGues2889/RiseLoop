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


class AuthCapability(BaseModel):
    """鉴权能力开关：上线前先确认这些接口都在，缺的是云资源而不是代码。"""

    refresh: bool = True
    revoke: bool = True
    account_delete: bool = True


class RateLimitCapability(BaseModel):
    requests: int
    window_seconds: int
    auth_requests: int


class CapabilitiesResponse(BaseModel):
    env: str
    version: str
    store_backend: str
    cloud_provider: str
    dependencies: list[ServiceStatus]
    auth: AuthCapability = AuthCapability()
    rate_limit: RateLimitCapability