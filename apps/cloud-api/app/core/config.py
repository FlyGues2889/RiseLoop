from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SITLOOP_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "SitLoop Cloud API"
    version: str = "0.1.0"
    env: str = "local"
    cloud_provider: Literal["mock", "huawei"] = "mock"
    cors_origins: list[str] = [
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ]

    jwt_secret: str = "sitloop-local-dev-secret-change-me"
    jwt_ttl_seconds: int = 3600

    sitting_threshold_minutes: int = 45
    push_cooldown_minutes: int = 10

    rds_dsn: str | None = None
    rds_host: str = ""
    rds_port: int = 5432
    rds_db: str = ""
    rds_user: str = ""
    rds_password: str = ""
    rds_pool_size: int = 5

    redis_url: str | None = None
    redis_host: str = ""
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    codearts_endpoint: str | None = None
    codearts_api_key: str | None = None
    codearts_planning_agent_id: str | None = None
    codearts_executing_agent_id: str | None = None
    codearts_timeout_seconds: float = 10.0

    obs_endpoint: str | None = None
    obs_bucket: str | None = None
    obs_region: str = ""
    obs_ak: str | None = None
    obs_sk: str | None = None

    kms_endpoint: str | None = None
    kms_key_id: str | None = None
    kms_master_key: str | None = None
    kms_ak: str | None = None
    kms_sk: str | None = None

    @property
    def store_backend(self) -> Literal["memory", "sql"]:
        if self.cloud_provider == "mock" and not self.rds_dsn:
            return "memory"
        return "sql"

    def resolved_rds_dsn(self) -> str | None:
        if self.rds_dsn:
            return self.rds_dsn
        if not (self.rds_host and self.rds_user and self.rds_db):
            return None
        password = quote_plus(self.rds_password)
        return (
            f"postgresql+asyncpg://{self.rds_user}:{password}"
            f"@{self.rds_host}:{self.rds_port}/{self.rds_db}"
        )

    def resolved_redis_url(self) -> str | None:
        if self.redis_url:
            return self.redis_url
        if not self.redis_host:
            return None
        auth = f":{quote_plus(self.redis_password)}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()