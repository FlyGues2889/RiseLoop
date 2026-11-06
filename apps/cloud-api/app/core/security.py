import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings

_ALG = "HS256"
_bearer = HTTPBearer(auto_error=False)


class TokenError(Exception):
    pass


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or uuid.uuid4().hex
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, _ = stored.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def _sign(message: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode(), message, hashlib.sha256).digest()


def encode_token(user_id: str, secret: str, ttl_seconds: int) -> str:
    header = {"alg": _ALG, "typ": "JWT"}
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + ttl_seconds, "jti": uuid.uuid4().hex}
    segments = [
        _b64encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64encode(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode()
    segments.append(_b64encode(_sign(signing_input, secret)))
    return ".".join(segments)


def decode_token(token: str, secret: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected = _sign(signing_input, secret)
        if not hmac.compare_digest(expected, _b64decode(signature_b64)):
            raise TokenError("bad_signature")
        payload = json.loads(_b64decode(payload_b64))
    except TokenError:
        raise
    except Exception as exc:
        raise TokenError("malformed_token") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise TokenError("expired")
    return payload


async def get_current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_token")
    settings: Settings = request.app.state.settings
    try:
        payload = decode_token(credentials.credentials, settings.jwt_secret)
    except TokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
    return str(payload["sub"])