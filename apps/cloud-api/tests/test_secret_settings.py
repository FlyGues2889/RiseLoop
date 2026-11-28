import json

import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_JWT_SECRET, Settings, secret_text


def test_settings_repr_redacts_secret_values():
    settings = Settings(
        cloud_provider="mock",
        jwt_secret="jwt-secret-value",
        rds_dsn="postgresql+asyncpg://user:rds-secret-value@db/riseloop",
        redis_url="redis://:redis-secret-value@cache:6379/0",
        obs_ak="obs-ak-value",
        obs_sk="obs-sk-value",
        obs_security_token="obs-token-value",
        kms_master_key="kms-master-value",
        modelarts_api_key="modelarts-key-value",
        codearts_api_key="codearts-key-value",
    )
    rendered = "\n".join(
        (
            repr(settings),
            str(settings),
            json.dumps(settings.model_dump(), default=str),
        )
    )
    for value in (
        "jwt-secret-value",
        "rds-secret-value",
        "redis-secret-value",
        "obs-ak-value",
        "obs-sk-value",
        "obs-token-value",
        "kms-master-value",
        "modelarts-key-value",
        "codearts-key-value",
    ):
        assert value not in rendered


def test_secret_text_reads_only_when_explicitly_requested():
    settings = Settings(cloud_provider="mock", jwt_secret="jwt-secret-value")
    assert secret_text(settings.jwt_secret) == "jwt-secret-value"
    assert secret_text(None) is None


@pytest.mark.parametrize("secret", ["", DEFAULT_JWT_SECRET, "change-me-in-huawei-kms"])
def test_production_rejects_insecure_jwt_secret(secret):
    with pytest.raises(ValidationError):
        Settings(env="prod", cloud_provider="mock", jwt_secret=secret)


def test_production_accepts_random_jwt_secret():
    settings = Settings(env="prod", cloud_provider="mock", jwt_secret="a" * 64)
    assert secret_text(settings.jwt_secret) == "a" * 64
