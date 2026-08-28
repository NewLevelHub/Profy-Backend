import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
    VerifyResetCodeRequest,
)
from app.services import auth_service, oauth_service, password_reset_service

router = APIRouter(tags=["auth"])

_redis: aioredis.Redis | None = None

_VERIFY_EMAIL_LIMIT = 10       # попыток
_VERIFY_EMAIL_WINDOW = 900     # 15 минут (совпадает со сроком жизни кода)
_VERIFY_RESET_LIMIT = 10
_VERIFY_RESET_WINDOW = 900
_FORGOT_IP_LIMIT = 3
_FORGOT_IP_WINDOW = 600        # 10 минут
_FORGOT_EMAIL_LIMIT = 3
_FORGOT_EMAIL_WINDOW = 600


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def _check_rate_limit(key: str, limit: int, window: int) -> None:
    redis = _get_redis()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await auth_service.register(body.email, body.password, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, token = await auth_service.login(body.email, body.password, db)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    except LookupError as exc:
        kind, email = str(exc).split(":", 1)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": kind, "email": email},
        )

    return TokenResponse(access_token=token, user=user)


@router.post("/google", response_model=TokenResponse)
async def google_login(body: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, token = await oauth_service.login_or_register_google(body.id_token, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return TokenResponse(access_token=token, user=user)


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    await _check_rate_limit(
        f"verify_email:{body.email}", _VERIFY_EMAIL_LIMIT, _VERIFY_EMAIL_WINDOW
    )
    try:
        user, token = await auth_service.verify_email(body.email, body.code, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return TokenResponse(access_token=token, user=user)


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(body: ResendVerificationRequest, db: AsyncSession = Depends(get_db)):
    rate_key = f"resend:{body.email}"
    redis = _get_redis()
    if await redis.exists(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait 60 seconds before requesting a new code",
        )

    await redis.set(rate_key, "1", ex=60)

    try:
        await auth_service.resend_verification(body.email, db)
    except ValueError:
        pass  # не раскрываем, существует ли email и верифицирован ли он


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(body: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    await _check_rate_limit(f"forgot_pwd_ip:{client_ip}", _FORGOT_IP_LIMIT, _FORGOT_IP_WINDOW)
    await _check_rate_limit(f"forgot_pwd_email:{body.email}", _FORGOT_EMAIL_LIMIT, _FORGOT_EMAIL_WINDOW)

    try:
        await password_reset_service.initiate_reset(body.email, db)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return {"message": "Reset code has been sent."}


@router.post("/verify-reset-code", status_code=status.HTTP_200_OK)
async def verify_reset_code(body: VerifyResetCodeRequest, db: AsyncSession = Depends(get_db)):
    await _check_rate_limit(
        f"verify_reset:{body.email}", _VERIFY_RESET_LIMIT, _VERIFY_RESET_WINDOW
    )
    try:
        await password_reset_service.verify_code(body.email, body.code, db)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code")
    return {"valid": True}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await _check_rate_limit(
        f"reset_pwd:{body.email}", _VERIFY_RESET_LIMIT, _VERIFY_RESET_WINDOW
    )
    try:
        await password_reset_service.reset_password(body.email, body.code, body.new_password, db)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code")
    return {"message": "Password has been reset successfully."}
