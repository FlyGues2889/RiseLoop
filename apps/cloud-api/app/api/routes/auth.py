from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import SettingsDep, StoreDep, UserIdDep
from ...core.config import Settings, secret_text
from ...core.security import (
    TokenError,
    decode_token,
    encode_token,
    get_token_claims,
    hash_password,
    verify_password,
)
from ...schemas.assessment import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(user_id: str, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=encode_token(user_id, secret_text(settings.jwt_secret), settings.jwt_ttl_seconds),
        expires_in=settings.jwt_ttl_seconds,
        refresh_token=encode_token(
            user_id, secret_text(settings.jwt_secret), settings.jwt_refresh_ttl_seconds, "refresh"
        ),
        refresh_expires_in=settings.jwt_refresh_ttl_seconds,
    )


def _expiry(claims: dict) -> datetime:
    return datetime.fromtimestamp(int(claims.get("exp", 0)), UTC)


async def _revoke(store, claims: dict) -> None:
    jti = claims.get("jti")
    if jti:
        await store.revoke_token(str(jti), _expiry(claims))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, store: StoreDep, settings: SettingsDep) -> TokenResponse:
    existing = await store.get_user_by_email(payload.email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_exists")
    user = await store.create_user(payload.email, hash_password(payload.password))
    return _tokens(user.id, settings)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, store: StoreDep, settings: SettingsDep) -> TokenResponse:
    user = await store.get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    return _tokens(user.id, settings)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, store: StoreDep, settings: SettingsDep) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, secret_text(settings.jwt_secret))
    except TokenError as exc:
        # 过期与伪造分开说，但都只影响续期，不需要再走一次密码
        detail = "refresh_expired" if str(exc) == "expired" else "invalid_refresh_token"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail) from exc
    if claims.get("typ") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_refresh_token"
        )
    if await store.is_token_revoked(str(claims.get("jti", ""))):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_revoked")
    user = await store.get_user(str(claims["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_refresh_token"
        )
    # 轮换刷新令牌：旧的立刻作废，避免被截获后重复使用
    await _revoke(store, claims)
    return _tokens(user.id, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    store: StoreDep,
    settings: SettingsDep,
    claims: dict = Depends(get_token_claims),
    payload: LogoutRequest | None = None,
) -> None:
    await _revoke(store, claims)
    if payload is not None and payload.refresh_token:
        try:
            refresh_claims = decode_token(payload.refresh_token, secret_text(settings.jwt_secret))
        except TokenError:
            refresh_claims = None
        if refresh_claims is not None:
            await _revoke(store, refresh_claims)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(user_id: UserIdDep, store: StoreDep) -> None:
    deleted = await store.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
