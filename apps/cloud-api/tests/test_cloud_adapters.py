import base64

import pytest
from cryptography.exceptions import InvalidTag

from app.cloud.kms import KmsService
from app.cloud.modelarts import ModelArtsService
from app.cloud.obs import ObsService
from app.core.config import Settings


def _settings(**overrides) -> Settings:
    base = {"cloud_provider": "mock", "jwt_secret": "test-secret"}
    base.update(overrides)
    return Settings(**base)


@pytest.mark.asyncio
async def test_kms_roundtrip():
    service = KmsService(_settings())
    ciphertext = await service.encrypt("health-data".encode())
    assert ciphertext.startswith("v1:")
    assert await service.decrypt(ciphertext) == b"health-data"


@pytest.mark.asyncio
async def test_kms_rejects_tampered_ciphertext():
    service = KmsService(_settings())
    ciphertext = await service.encrypt(b"pain_score=3")
    raw = bytearray(base64.b64decode(ciphertext[3:]))
    raw[-1] ^= 0xFF
    tampered = "v1:" + base64.b64encode(bytes(raw)).decode()
    with pytest.raises(InvalidTag):
        await service.decrypt(tampered)


@pytest.mark.asyncio
async def test_kms_requires_master_key_in_huawei_mode():
    service = KmsService(_settings(cloud_provider="huawei", kms_endpoint="https://kms", kms_key_id="k"))
    with pytest.raises(RuntimeError):
        await service.encrypt(b"data")


@pytest.mark.asyncio
async def test_obs_mock_presign_is_explicit():
    service = ObsService(_settings())
    url = await service.presign_get("videos/demo.mp4")
    assert url.startswith("mock://obs/")


@pytest.mark.asyncio
async def test_obs_huawei_presign_contains_signature():
    service = ObsService(
        _settings(
            cloud_provider="huawei",
            obs_endpoint="https://riseloop.obs.cn-north-4.myhuaweicloud.com",
            obs_bucket="riseloop",
            obs_ak="AK",
            obs_sk="SK",
        )
    )
    url = await service.presign_put("exports/weekly.json", expires_seconds=600)
    assert url.startswith("https://riseloop.obs.cn-north-4.myhuaweicloud.com/exports/weekly.json?")
    assert "AccessKeyId=AK" in url
    assert "Signature=" in url


@pytest.mark.asyncio
async def test_obs_presign_carries_temporary_security_token():
    service = ObsService(
        _settings(
            cloud_provider="huawei",
            obs_endpoint="https://riseloop.obs.cn-north-4.myhuaweicloud.com",
            obs_bucket="riseloop",
            obs_ak="AK",
            obs_sk="SK",
            obs_security_token="temporary-token",
        )
    )
    url = await service.presign_get("exports/weekly.json", expires_seconds=600)
    assert "SecurityToken=temporary-token" in url


@pytest.mark.asyncio
async def test_obs_requires_configuration_in_huawei_mode():
    service = ObsService(_settings(cloud_provider="huawei"))
    with pytest.raises(RuntimeError):
        await service.presign_get("videos/demo.mp4")


def test_modelarts_apig_appcode_header():
    service = ModelArtsService(
        _settings(
            cloud_provider="huawei",
            modelarts_api_key="appcode-value",
            modelarts_auth_header="x-apig-appcode",
        )
    )
    assert service._headers() == {
        "Content-Type": "application/json",
        "X-Apig-AppCode": "appcode-value",
    }