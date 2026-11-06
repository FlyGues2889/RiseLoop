import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..core.config import Settings
from .base import ServiceStatus

KEY_BYTES = 32
NONCE_BYTES = 12
AAD = b"riseloop:field"


class KmsService:
    name = "kms"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(self._settings.kms_endpoint and self._settings.kms_key_id)

    def _master_key(self) -> bytes:
        if self._settings.kms_master_key:
            key = base64.b64decode(self._settings.kms_master_key)
            if len(key) != KEY_BYTES:
                raise ValueError("kms_master_key must be 32 bytes base64 encoded")
            return key
        if self._settings.cloud_provider == "mock":
            return hashlib.sha256(self._settings.jwt_secret.encode()).digest()
        raise RuntimeError("kms_master_key is not configured")

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
                provider="huawei-kms",
                configured=False,
                reachable=None,
                detail="kms_credentials_not_configured",
            )
        return ServiceStatus(
            name=self.name,
            provider="huawei-kms",
            configured=True,
            reachable=None,
            detail="field_encryption_ready",
        )

    async def encrypt(self, plaintext: bytes) -> str:
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(self._master_key()).encrypt(nonce, plaintext, AAD)
        return "v1:" + base64.b64encode(nonce + ciphertext).decode()

    async def decrypt(self, ciphertext: str) -> bytes:
        if not ciphertext.startswith("v1:"):
            raise ValueError("unsupported ciphertext version")
        raw = base64.b64decode(ciphertext[3:])
        if len(raw) <= NONCE_BYTES:
            raise ValueError("ciphertext is too short")
        return AESGCM(self._master_key()).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], AAD)

    async def close(self) -> None:
        return None