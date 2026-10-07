import hashlib
import hmac
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.catalog import key as i18n_key
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.i18n import KNOWN_LOCALES, normalize_locale
from app.models.user import User
from app.schemas.invitation import AcceptInvitationRequest, InvitationPreview
from app.schemas.auth import (
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateMeRequest,
    UserResponse,
    VerifyEmailRequest,
    VerifyResetCodeRequest,
)
from app.services import auth_service, invitation_service, oauth_service, password_reset_service

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None

_VERIFY_EMAIL_LIMIT = 10       # попыток
_VERIFY_EMAIL_WINDOW = 900     # 15 минут (совпадает со сроком жизни кода)
_VERIFY_RESET_LIMIT = 10
_VERIFY_RESET_WINDOW = 900
_FORGOT_IP_LIMIT = 3
_FORGOT_IP_WINDOW = 600        # 10 минут
_FORGOT_EMAIL_LIMIT = 3
_FORGOT_EMAIL_WINDOW = 600
_REGISTER_IP_LIMIT = 5
_REGISTER_IP_WINDOW = 600      # 10 минут
_LOGIN_IP_LIMIT = 30
_LOGIN_IP_WINDOW = 900
_LOGIN_EMAIL_LIMIT = 5
_LOGIN_EMAIL_WINDOW = 900
# Staff invitations (PRO-462), per client IP. Preview runs on every /invite
# page load, so it gets more headroom than the password-setting accept.
_INVITATION_PREVIEW_IP_LIMIT = 30
_INVITATION_ACCEPT_IP_LIMIT = 10
_INVITATION_IP_WINDOW = 900

_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_rate_key(scope: str, value: str) -> str:
    """Build a stable Redis key without retaining an email or IP as PII."""
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"{scope}:{value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"login_{scope}:{digest}"


def _login_email_rate_key(email: str) -> str:
    return _login_rate_key("email", str(email).strip().lower())


def _login_ip_rate_key(ip: str) -> str:
    return _login_rate_key("ip", ip)


async def _increment_rate_limit(key: str, window: int) -> tuple[int, int]:
    redis = _get_redis()
    # INCR and first-key expiry must be atomic. Otherwise a worker stopping
    # between the two commands can leave a permanent lockout key behind.
    count, ttl = await redis.eval(_RATE_LIMIT_SCRIPT, 1, key, window)
    return int(count), int(ttl)


def _raise_rate_limit(scope: str, count: int, ttl: int) -> None:
    retry_after = max(ttl, 1)
    logger.warning(
        "Authentication rate limit exceeded: scope=%s count=%s retry_after=%s",
        scope,
        count,
        retry_after,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=i18n_key("api_errors", "rate_limit_exceeded"),
        headers={"Retry-After": str(retry_after)},
    )


async def _check_rate_limit(
    key: str,
    limit: int,
    window: int,
    *,
    scope: str = "auth",
) -> None:
    count, ttl = await _increment_rate_limit(key, window)
    if count > limit:
        _raise_rate_limit(scope, count, ttl)


async def _reject_if_rate_limited(key: str, limit: int, *, scope: str) -> None:
    redis = _get_redis()
    count = await redis.get(key)
    if count is None or int(count) < limit:
        return
    _raise_rate_limit(scope, int(count), int(await redis.ttl(key)))


async def _record_login_failure(ip_key: str, email_key: str) -> None:
    # Both dimensions are recorded even when one of them crosses its limit,
    # so a concurrent burst cannot evade the other limiter.
    ip_count, ip_ttl = await _increment_rate_limit(ip_key, _LOGIN_IP_WINDOW)
    email_count, email_ttl = await _increment_rate_limit(
        email_key, _LOGIN_EMAIL_WINDOW
    )
    if ip_count > _LOGIN_IP_LIMIT:
        _raise_rate_limit("login_ip", ip_count, ip_ttl)
    if email_count > _LOGIN_EMAIL_LIMIT:
        _raise_rate_limit("login_email", email_count, email_ttl)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = _client_ip(request)
    await _check_rate_limit(f"register_ip:{client_ip}", _REGISTER_IP_LIMIT, _REGISTER_IP_WINDOW)
    # Seed the new user's UI locale from Accept-Language. KNOWN_LOCALES (not the
    # runtime gate) so a "kk" browser preference is preserved for KZ-603; the
    # user can still change it via PATCH /auth/me.
    locale = normalize_locale(request.headers.get("accept-language"), allowed=KNOWN_LOCALES)
    try:
        return await auth_service.register(body.email, body.password, db, locale=locale)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    client_ip = _client_ip(request)
    ip_rate_key = _login_ip_rate_key(client_ip)
    email_rate_key = _login_email_rate_key(body.email)
    await _reject_if_rate_limited(
        ip_rate_key,
        _LOGIN_IP_LIMIT,
        scope="login_ip",
    )
    await _reject_if_rate_limited(
        email_rate_key,
        _LOGIN_EMAIL_LIMIT,
        scope="login_email",
    )

    try:
        user, token = await auth_service.login(body.email, body.password, db)
    except PermissionError as exc:
        await _record_login_failure(ip_rate_key, email_rate_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    except LookupError as exc:
        kind, email = str(exc).split(":", 1)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": kind, "email": email},
        )

    # The account counter represents consecutive unsuccessful attempts. The
    # IP counter already contains failures only and is deliberately retained,
    # so rotating through many accounts cannot bypass credential-stuffing
    # protection. Successful logins never consume the shared IP budget.
    await _get_redis().delete(email_rate_key)
    return TokenResponse(access_token=token, user=user)


@router.post("/google", response_model=TokenResponse)
async def google_login(body: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, token = await oauth_service.login_or_register_google(body.id_token, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return TokenResponse(access_token=token, user=user)


@router.get("/invitations/{token}", response_model=InvitationPreview)
async def preview_invitation(
    token: str, request: Request, db: AsyncSession = Depends(get_db)
) -> InvitationPreview:
    await _check_rate_limit(
        f"invitation_preview_ip:{_client_ip(request)}",
        _INVITATION_PREVIEW_IP_LIMIT,
        _INVITATION_IP_WINDOW,
    )
    return await invitation_service.preview_invitation(db, token)


@router.post("/invitations/accept", response_model=TokenResponse)
async def accept_invitation(
    body: AcceptInvitationRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    await _check_rate_limit(
        f"invitation_accept_ip:{_client_ip(request)}",
        _INVITATION_ACCEPT_IP_LIMIT,
        _INVITATION_IP_WINDOW,
    )
    user, token = await invitation_service.accept_invitation(db, body)
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
            detail=i18n_key("api_errors", "verification_resend_too_soon", locale="ru"),
        )

    await redis.set(rate_key, "1", ex=60)

    try:
        await auth_service.resend_verification(body.email, db)
    except ValueError:
        pass  # не раскрываем, существует ли email и верифицирован ли он


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale_changed = current_user.locale != body.locale
    current_user.locale = body.locale
    current_user.locale_explicit = True
    await db.commit()
    await db.refresh(current_user)
    if locale_changed:
        # The report is generated in the owner's language (KZ-403/405); drop
        # the cached owner-locale pointer + per-locale report cache so the
        # next /result read resolves the new language (KZ-406).
        from app.services import report_service
        await report_service.invalidate_owner_locale_cache(current_user.id, db)
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(body: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = _client_ip(request)
    await _check_rate_limit(f"forgot_pwd_ip:{client_ip}", _FORGOT_IP_LIMIT, _FORGOT_IP_WINDOW)
    await _check_rate_limit(f"forgot_pwd_email:{body.email}", _FORGOT_EMAIL_LIMIT, _FORGOT_EMAIL_WINDOW)

    try:
        await password_reset_service.initiate_reset(body.email, db)
    except ValueError:
        # Не раскрываем, зарегистрирован ли адрес: ответ одинаков в обоих
        # случаях, иначе форма становится оракулом для перебора почт. Тот же
        # приём, что и в /resend-verification выше.
        pass
    return {"message": i18n_key("api_messages", "password_reset_requested")}


@router.post("/verify-reset-code", status_code=status.HTTP_200_OK)
async def verify_reset_code(body: VerifyResetCodeRequest, db: AsyncSession = Depends(get_db)):
    await _check_rate_limit(
        f"verify_reset:{body.email}", _VERIFY_RESET_LIMIT, _VERIFY_RESET_WINDOW
    )
    try:
        await password_reset_service.verify_code(body.email, body.code, db)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=i18n_key("api_errors", "invalid_or_expired_code", locale="ru"))
    return {"valid": True}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await _check_rate_limit(
        f"reset_pwd:{body.email}", _VERIFY_RESET_LIMIT, _VERIFY_RESET_WINDOW
    )
    try:
        await password_reset_service.reset_password(body.email, body.code, body.new_password, db)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=i18n_key("api_errors", "invalid_or_expired_code", locale="ru"))
    return {"message": i18n_key("api_messages", "password_reset_completed")}
