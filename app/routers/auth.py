import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from fastapi import Request

from app.schemas.auth import (
    ForgotPasswordRequest,
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
from app.services import auth_service, password_reset_service

router = APIRouter(tags=["auth"])

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


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
        _, email = str(exc).split(":", 1)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "email_not_verified", "email": email},
        )

    return TokenResponse(access_token=token, user_id=user.id)


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, token = await auth_service.verify_email(body.email, body.code, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return TokenResponse(access_token=token, user_id=user.id)


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(body: ResendVerificationRequest, db: AsyncSession = Depends(get_db)):
    rate_key = f"resend:{body.email}"
    redis = _get_redis()
    if await redis.exists(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait 60 seconds before requesting a new code",
        )

    try:
        await auth_service.resend_verification(body.email, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await redis.set(rate_key, "1", ex=60)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(body: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"forgot_pwd:{client_ip}"
    redis = _get_redis()

    count = await redis.incr(rate_key)
    if count == 1:
        await redis.expire(rate_key, 600)
    if count > 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

    await password_reset_service.initiate_reset(body.email, db)
    return {"message": "If this email exists, a reset code has been sent."}


@router.post("/verify-reset-code", status_code=status.HTTP_200_OK)
async def verify_reset_code(body: VerifyResetCodeRequest, db: AsyncSession = Depends(get_db)):
    try:
        await password_reset_service.verify_code(body.email, body.code, db)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code")
    return {"valid": True}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    try:
        await password_reset_service.reset_password(body.email, body.code, body.new_password, db)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code")
    return {"message": "Password has been reset successfully."}
