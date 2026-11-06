from time import perf_counter

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..core.config import Settings
from .base import ServiceStatus


class RdsService:
    name = "rds"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._dsn = settings.resolved_rds_dsn()
        self._engine: AsyncEngine | None = None

    def _get_engine(self) -> AsyncEngine | None:
        if self._engine is None and self._dsn:
            self._engine = create_async_engine(
                self._dsn,
                pool_size=self._settings.rds_pool_size,
                pool_pre_ping=True,
            )
        return self._engine

    async def check(self) -> ServiceStatus:
        if self._settings.cloud_provider == "mock":
            return ServiceStatus(
                name=self.name,
                provider="mock",
                configured=True,
                reachable=True,
                detail="mock provider",
            )
        if not self._dsn:
            return ServiceStatus(
                name=self.name,
                provider="huawei-rds",
                configured=False,
                reachable=None,
                detail="dsn_not_configured",
            )

        started = perf_counter()
        try:
            engine = self._get_engine()
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return ServiceStatus(
                name=self.name,
                provider="huawei-rds",
                configured=True,
                reachable=True,
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            return ServiceStatus(
                name=self.name,
                provider="huawei-rds",
                configured=True,
                reachable=False,
                detail=type(exc).__name__,
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

    async def execute(self, statement: str, params: dict | None = None):
        engine = self._get_engine()
        if engine is None:
            raise RuntimeError("RDS is not configured")
        async with engine.begin() as connection:
            return await connection.execute(text(statement), params or {})

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None