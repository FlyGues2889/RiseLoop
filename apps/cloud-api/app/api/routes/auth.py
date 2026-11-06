from fastapi import APIRouter, HTTPException, status

from ..deps import SettingsDep, StoreDep
from ...core.security import encode_token, hash_password, verify_password
from ...schemas.assessment import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, store: StoreDep, settings: SettingsDep) -> TokenResponse:
    existing = await store.get_user_by_email(payload.email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_exists")
    user = await store.create_user(payload.email, hash_password(payload.password))
    return TokenResponse(
        access_token=encode_token(user.id, settings.jwt_secret, settings.jwt_ttl_seconds),
        expires_in=settings.jwt_ttl_seconds,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, store: StoreDep, settings: SettingsDep) -> TokenResponse:
    user = await store.get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    return TokenResponse(
        access_token=encode_token(user.id, settings.jwt_secret, settings.jwt_ttl_seconds),
        expires_in=settings.jwt_ttl_seconds,
    )