import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlparse

from ..core.config import Settings
from .base import ServiceStatus


class ObsService:
    name = "obs"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.obs_endpoint
            and self._settings.obs_bucket
            and self._settings.obs_ak
            and self._settings.obs_sk
        )

    def _scheme(self) -> str:
        return "http" if (self._settings.obs_endpoint or "").startswith("http://") else "https"

    def _host(self) -> str:
        endpoint = self._settings.obs_endpoint or ""
        parsed = urlparse(endpoint)
        return parsed.netloc or endpoint

    def _signature(self, method: str, key: str, expires_at: int) -> str:
        object_path = "/" + quote(key.lstrip("/"), safe="/")
        string_to_sign = (
            f"{method}\n\n\n{expires_at}\n/{self._settings.obs_bucket}{object_path}"
        )
        digest = hmac.new(
            (self._settings.obs_sk or "").encode(),
            string_to_sign.encode(),
            hashlib.sha1,
        ).digest()
        return quote(base64.b64encode(digest).decode(), safe="")

    def _presign(self, method: str, key: str, expires_seconds: int) -> str:
        object_path = "/" + quote(key.lstrip("/"), safe="/")
        if self._settings.cloud_provider == "mock":
            return f"mock://obs/{self._settings.obs_bucket}{object_path}?method={method}"

        if not self.configured:
            raise RuntimeError("OBS credentials are not configured")
        if expires_seconds <= 0:
            raise ValueError("expires_seconds must be positive")

        expires_at = int(
            (datetime.now(UTC) + timedelta(seconds=expires_seconds)).timestamp()
        )
        signature = self._signature(method, key, expires_at)
        return (
            f"{self._scheme()}://{self._host()}{object_path}"
            f"?AccessKeyId={self._settings.obs_ak}"
            f"&Expires={expires_at}"
            f"&Signature={signature}"
        )

    async def check(self) -> ServiceStatus:
        if self._settings.cloud_provider == "mock":
            return ServiceStatus(
                name=self.name,
                provider="mock",
                configured=True,
                reachable=True,
                detail="mock provider",
            )
        if not self.configured:
            return ServiceStatus(
                name=self.name,
                provider="huawei-obs",
                configured=False,
                reachable=None,
                detail="obs_credentials_not_configured",
            )
        return ServiceStatus(
            name=self.name,
            provider="huawei-obs",
            configured=True,
            reachable=None,
            detail="presign_ready",
        )

    async def presign_put(self, key: str, expires_seconds: int = 3600) -> str:
        return self._presign("PUT", key, expires_seconds)

    async def presign_get(self, key: str, expires_seconds: int = 3600) -> str:
        return self._presign("GET", key, expires_seconds)

    async def close(self) -> None:
        return None