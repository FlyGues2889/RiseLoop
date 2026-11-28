from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "riseloop-local-dev-secret-change-me"
INSECURE_JWT_SECRETS = {
    "",
    DEFAULT_JWT_SECRET,
    "change-me-in-huawei-kms",
    "change-me-to-a-random-64-char-string",
}


def secret_text(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value is not None else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RISELOOP_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Rise Loop Cloud API"
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

    jwt_secret: SecretStr = SecretStr(DEFAULT_JWT_SECRET)
    jwt_ttl_seconds: int = 3600
    # 刷新令牌只管"续期"，生命周期比访问令牌长；吊销靠 jti 黑名单
    jwt_refresh_ttl_seconds: int = 60 * 60 * 24 * 30

    # 接口限流：默认按键（登录态用 token 指纹，否则用来源 IP）计数
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    rate_limit_auth_requests: int = 10

    sitting_threshold_minutes: int = 45
    push_cooldown_minutes: int = 10

    rds_dsn: SecretStr | None = None
    rds_host: str = ""
    rds_port: int = 5432
    rds_db: str = ""
    rds_user: str = ""
    rds_password: SecretStr = SecretStr("")
    rds_pool_size: int = 5

    redis_url: SecretStr | None = None
    redis_host: str = ""
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: SecretStr | None = None

    codearts_endpoint: str | None = None
    codearts_api_key: SecretStr | None = None
    codearts_planning_agent_id: str | None = None
    codearts_executing_agent_id: str | None = None
    codearts_timeout_seconds: float = 10.0

    obs_endpoint: str | None = None
    obs_bucket: str | None = None
    obs_region: str = ""
    # AK/SK 只从环境或密钥管理注入；SecretStr 阻止 repr/日志泄漏。
    obs_ak: SecretStr | None = None
    obs_sk: SecretStr | None = None
    # 临时凭证（IAM 委托/STS）随 AK/SK 一起签名；静态密钥不应设置此项。
    obs_security_token: SecretStr | None = None

    kms_endpoint: str | None = None
    kms_key_id: str | None = None
    kms_master_key: SecretStr | None = None

    modelarts_endpoint: str | None = None
    modelarts_api_key: SecretStr | None = None
    modelarts_project_id: str | None = None
    modelarts_model_name: str = "riseloop-posture-v3"
    modelarts_auth_header: Literal[
        "x-auth-token", "authorization", "x-api-key", "x-apig-appcode"
    ] = "x-auth-token"
    modelarts_timeout_seconds: float = 2.5
    modelarts_tls_verify: bool = True
    # mock 只用于联调；演示前可设为 unavailable，让 /posture/infer 明确 503 降级。
    posture_mock_policy: Literal["heuristic", "unavailable"] = "heuristic"

    @model_validator(mode="after")
    def _reject_default_production_secret(self) -> "Settings":
        if self.env.lower() in ("prod", "production"):
            if secret_text(self.jwt_secret) in INSECURE_JWT_SECRETS:
                raise ValueError(
                    "RISELOOP_JWT_SECRET must be set to a non-default value when RISELOOP_ENV=prod"
                )
        return self

    @property
    def store_backend(self) -> Literal["memory", "sql"]:
        if self.cloud_provider == "mock" and not secret_text(self.rds_dsn):
            return "memory"
        return "sql"

    def resolved_rds_dsn(self) -> str | None:
        dsn = secret_text(self.rds_dsn)
        if dsn:
            return dsn
        if not (self.rds_host and self.rds_user and self.rds_db):
            return None
        password = quote_plus(secret_text(self.rds_password) or "")
        return (
            f"postgresql+asyncpg://{self.rds_user}:{password}"
            f"@{self.rds_host}:{self.rds_port}/{self.rds_db}"
        )

    def resolved_redis_url(self) -> str | None:
        url = secret_text(self.redis_url)
        if url:
            return url
        if not self.redis_host:
            return None
        password = secret_text(self.redis_password)
        auth = f":{quote_plus(password)}@" if password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()