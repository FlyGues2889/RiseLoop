import json
import os
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

SESSION_KEY = "session:{user}:state"
SITTING_KEY = "sitting:{user}:timer"
PENDING_KEY = "pending_intervention:{user}"
SAFETY_KEY = "safety:{user}:ttl"


def session_key(user_id: str) -> str:
    return SESSION_KEY.format(user=user_id)


def sitting_key(user_id: str) -> str:
    return SITTING_KEY.format(user=user_id)


def pending_key(user_id: str) -> str:
    return PENDING_KEY.format(user=user_id)


class RealtimeState(BaseModel):
    user_id: str
    state: str
    counters: dict = Field(default_factory=dict)
    sitting_minutes: int = 0
    last_push_at: str | None = None
    pending_intervention: dict | None = None


@dataclass
class Backend:
    redis: object
    pg: object
    database_url: str | None = None
    _pool: object | None = field(default=None, repr=False)

    async def redis_get(self, key: str) -> str | None:
        return await self.redis.get(key)

    async def redis_set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        await self.redis.set(key, value, ex=ttl_seconds)

    async def redis_delete(self, key: str) -> None:
        await self.redis.delete(key)

    async def fetch(self, query: str, *args):
        return await self.pg.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        return await self.pg.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        return await self.pg.fetchval(query, *args)


class MemoryRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)


def build_backend() -> Backend:
    import redis.asyncio as aioredis

    redis_url = os.environ.get("RISELOOP_REDIS_URL") or "redis://127.0.0.1:6379/0"
    database_url = os.environ.get("RISELOOP_RDS_DSN") or os.environ.get("RISELOOP_DATABASE_URL")
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    return Backend(redis=redis_client, pg=_PgProxy(database_url), database_url=database_url)


class _PgProxy:
    def __init__(self, dsn: str | None) -> None:
        self._dsn = dsn
        self._pool = None

    async def _ensure(self):
        if self._pool is None:
            import asyncpg

            if not self._dsn:
                raise RuntimeError("RISELOOP_RDS_DSN is required for SQL tools")
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        return self._pool

    async def fetch(self, query: str, *args):
        pool = await self._ensure()
        async with pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        pool = await self._ensure()
        async with pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        pool = await self._ensure()
        async with pool.acquire() as connection:
            return await connection.fetchval(query, *args)


def dump(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)