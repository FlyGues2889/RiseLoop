from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..core.config import Settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_sessionmaker(settings: Settings) -> async_sessionmaker[AsyncSession] | None:
    global _engine, _sessionmaker
    dsn = settings.resolved_rds_dsn()
    if _engine is not None or not dsn:
        return _sessionmaker
    _engine = create_async_engine(dsn, pool_size=settings.rds_pool_size, pool_pre_ping=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


def get_sessionmaker() -> async_sessionmaker[AsyncSession] | None:
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None