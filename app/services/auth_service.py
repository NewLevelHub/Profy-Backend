import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.catalog import key as i18n_key
from app.config import settings
from app.models.email_verification import EmailVerificationToken
from app.models.user import User
from app.schemas.auth import RegisterResponse
from app.services import email_service, invitation_service
from app.services.crm import invites
from app.services.token_utils import code_matches, generate_code, hash_code, record_failed_attempt

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_jwt_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "ver": user.token_version,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def revoke_sessions(user: User, db: AsyncSession) -> None:
    """Sign the account out everywhere. Every access token carries the
    `ver` it was issued under (`create_jwt_token`) and stops validating the
    moment the stored version moves on — the same switch a password reset
    uses. Incremented in SQL, so a logout racing a reset loses neither."""
    await db.execute(
        update(User).where(User.id == user.id).values(token_version=User.token_version + 1)
    )
    await db.commit()


async def _invalidate_tokens(user_id: uuid.UUID, db: AsyncSession) -> None:
    await db.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.user_id == user_id,
            EmailVerificationToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(timezone.utc))
    )


async def _create_verification_token(user_id: uuid.UUID, db: AsyncSession) -> str:
    await _invalidate_tokens(user_id, db)
    code = generate_code()
    token = EmailVerificationToken(
        user_id=user_id,
        code_hash=hash_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(token)
    await db.flush()
    return code


async def register(
    email: str, password: str, db: AsyncSession, *, locale: str = "ru", student_invite: str | None = None
) -> RegisterResponse:
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ValueError(i18n_key("api_errors", "email_already_exists", locale="ru"))
    # An invited staff member who wandered off /invite would get a student
    # account here, and a verified one blocks the invitation for good.
    if await invitation_service.has_pending(db, email):
        raise invitation_service.invitation_error(status.HTTP_409_CONFLICT, "invited_email_register")
    # Paid service: a new student comes only with the CRM link. The link is
    # used up once the verified student opens it (POST /student-invites/accept).
    await invites.require_open_invite(db, student_invite)

    user = User(
        email=email,
        hashed_password=hash_password(password),
        is_verified=False,
        locale=locale,
    )
    db.add(user)
    await db.flush()

    code = await _create_verification_token(user.id, db)
    await db.commit()

    try:
        await email_service.send_verification_email(email, code, locale=locale)
    except Exception:
        logger.exception("Failed to send verification email during registration for %s", email)

    return RegisterResponse(user_id=user.id, email=email, message=i18n_key("api_messages", "verification_code_sent", locale=locale))


async def login(email: str, password: str, db: AsyncSession) -> tuple[User, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        # No account yet, but an open invitation: it is made from the link.
        if await invitation_service.has_pending(db, email):
            raise LookupError(f"invitation_pending:{email}")
        raise PermissionError(i18n_key("api_errors", "invalid_credentials", locale="ru"))

    if user.hashed_password is None:
        raise LookupError(f"google_account:{user.email}")

    if not verify_password(password, user.hashed_password):
        raise PermissionError(i18n_key("api_errors", "invalid_credentials", locale="ru"))

    if not user.is_verified:
        raise LookupError(f"email_not_verified:{user.email}")

    return user, create_jwt_token(user)


def _code_rejected() -> ValueError:
    # One answer for every way a code fails — unknown address, no live code,
    # expired, wrong digits: telling them apart would let anyone check
    # whether an email is registered and waiting for verification.
    return ValueError(i18n_key("api_errors", "invalid_or_expired_code", locale="ru"))


async def verify_email(email: str, code: str, db: AsyncSession) -> tuple[User, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise _code_rejected()

    # Locked: guesses at one code are checked and counted one at a time, so a
    # parallel burst cannot try more values than the code has attempts.
    token_result = await db.execute(
        select(EmailVerificationToken)
        .where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
        )
        .order_by(EmailVerificationToken.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    token = token_result.scalar_one_or_none()

    if not token:
        raise _code_rejected()

    now = datetime.now(timezone.utc)
    expires = token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if now > expires:
        raise _code_rejected()

    if not code_matches(token.code_hash, code):
        record_failed_attempt(token)
        await db.commit()
        raise _code_rejected()

    if not user.is_verified:
        # An invited address is never confirmed with this code. The account
        # was registered by whoever typed the address — not necessarily its
        # owner — and keeps the password they chose; six digits must not be
        # what turns it into staff. It stays unverified, and the invitation
        # link (or a Google login on the address) takes it over. The lock
        # orders this against a concurrent create — either the invitation
        # is seen here, or create sees the verified account.
        await invitation_service.lock_email(db, user.email)
        if await invitation_service.has_pending(db, user.email):
            raise invitation_service.invitation_error(status.HTTP_409_CONFLICT, "invited_email_register")
    token.used_at = now
    user.is_verified = True
    await db.commit()
    await db.refresh(user)

    return user, create_jwt_token(user)


async def resend_verification(email: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(i18n_key("api_errors", "user_not_found", locale="ru"))
    if user.is_verified:
        raise ValueError(i18n_key("api_errors", "email_already_verified", locale="ru"))

    code = await _create_verification_token(user.id, db)
    await db.commit()

    try:
        await email_service.send_verification_email(email, code, locale=user.locale)
    except Exception:
        logger.exception("Failed to send verification email during resend for %s", email)
