from typing import Protocol

from pydantic import BaseModel


class ServiceStatus(BaseModel):
    name: str
    provider: str
    configured: bool
    reachable: bool | None
    detail: str | None = None
    latency_ms: float | None = None


class CloudService(Protocol):
    name: str

    async def check(self) -> ServiceStatus: ...

    async def close(self) -> None: ...