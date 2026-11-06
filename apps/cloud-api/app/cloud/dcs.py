from time import perf_counter

from redis.asyncio import Redis

from ..core.config import Settings
from .base import ServiceStatus


class DcsService:
    name = "redis"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._url = settings.resolved_redis_url()
        self._client: Redis | None = None

    def _get_client(self) -> Redis | None:
        if self._client is None and self._url:
            self._client = Redis.from_url(self._url, decode_responses=True)
        return self._client

    async def check(self) -> ServiceStatus:
        if self._settings.cloud_provider == "mock":
            return ServiceStatus(
                name=self.name,
                provider="mock",
                configured=True,
                reachable=True,
                detail="mock provider",
            )
        if not self._url:
            return ServiceStatus(
                name=self.name,
                provider="huawei-dcs",
                configured=False,
                reachable=None,
                detail="url_not_configured",
            )

        started = perf_counter()
        try:
            client = self._get_client()
            await client.ping()
            return ServiceStatus(
                name=self.name,
                provider="huawei-dcs",
                configured=True,
                reachable=True,
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            return ServiceStatus(
                name=self.name,
                provider="huawei-dcs",
                configured=True,
                reachable=False,
                detail=type(exc).__name__,
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

    async def get(self, key: str) -> str | None:
        client = self._get_client()
        if client is None:
            raise RuntimeError("DCS Redis is not configured")
        return await client.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        client = self._get_client()
        if client is None:
            raise RuntimeError("DCS Redis is not configured")
        await client.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        client = self._get_client()
        if client is None:
            raise RuntimeError("DCS Redis is not configured")
        await client.delete(key)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None