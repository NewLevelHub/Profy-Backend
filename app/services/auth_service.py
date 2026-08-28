import logging
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_verification import EmailVerificationToken
from app.models.user import User
from app.schemas.auth import RegisterResponse
from app.services import email_service
from app.services.token_utils import generate_code, hash_code

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_jwt_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


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


async def register(email: str, password: str, db: AsyncSession) -> RegisterResponse:
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ValueError("Email already exists")

    user = User(email=email, hashed_password=hash_password(password), is_verified=False)
    db.add(user)
    await db.flush()

    code = await _create_verification_token(user.id, db)
    await db.commit()

    try:
        await email_service.send_verification_email(email, code)
    except Exception:
        logger.exception("Failed to send verification email during registration for %s", email)

    return RegisterResponse(user_id=user.id, email=email, message="Код отправлен на почту")


async def login(email: str, password: str, db: AsyncSession) -> tuple[User, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise PermissionError("Invalid credentials")

    if user.hashed_password is None:
        raise LookupError(f"google_account:{user.email}")

    if not verify_password(password, user.hashed_password):
        raise PermissionError("Invalid credentials")

    if not user.is_verified:
        raise LookupError(f"email_not_verified:{user.email}")

    return user, create_jwt_token(user.id)


async def verify_email(email: str, code: str, db: AsyncSession) -> tuple[User, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    token_result = await db.execute(
        select(EmailVerificationToken)
        .where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
        )
        .order_by(EmailVerificationToken.created_at.desc())
        .limit(1)
    )
    token = token_result.scalar_one_or_none()

    if not token:
        raise ValueError("No active verification code")

    now = datetime.now(timezone.utc)
    expires = token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if now > expires:
        raise ValueError("Verification code expired")

    if token.code_hash != hash_code(code):
        raise ValueError("Invalid verification code")

    token.used_at = now
    user.is_verified = True
    await db.commit()
    await db.refresh(user)

    return user, create_jwt_token(user.id)


async def resend_verification(email: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")
    if user.is_verified:
        raise ValueError("Email already verified")

    code = await _create_verification_token(user.id, db)
    await db.commit()

    try:
        await email_service.send_verification_email(email, code)
    except Exception:
        logger.exception("Failed to send verification email during resend for %s", email)
