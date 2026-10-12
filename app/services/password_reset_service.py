import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services import email_service
from app.services.auth_service import hash_password
from app.services.token_utils import code_matches, generate_code, hash_code, record_failed_attempt

logger = logging.getLogger(__name__)


async def _invalidate_reset_tokens(user_id: uuid.UUID, db: AsyncSession) -> None:
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(timezone.utc))
    )


async def _get_active_token(user_id: uuid.UUID, db: AsyncSession) -> PasswordResetToken | None:
    # Locked: guesses at one code are checked and counted one at a time, so a
    # parallel burst cannot try more values than the code has attempts.
    result = await db.execute(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
        .order_by(PasswordResetToken.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _require_valid_code(user_id: uuid.UUID, code: str, db: AsyncSession) -> None:
    """Raise unless `code` is the account's live reset code. A wrong guess is
    committed against the code before raising — both endpoints that accept
    the code go through here, so they share its attempts."""
    token = await _get_active_token(user_id, db)
    if not token:
        raise ValueError("Invalid code")

    now = datetime.now(timezone.utc)
    expires = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    if now > expires:
        raise ValueError("Code expired")

    if not code_matches(token.code_hash, code):
        record_failed_attempt(token)
        await db.commit()
        raise ValueError("Invalid code")


async def initiate_reset(email: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("Account not found")

    await _invalidate_reset_tokens(user.id, db)

    code = generate_code()
    token = PasswordResetToken(
        user_id=user.id,
        code_hash=hash_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(token)
    await db.commit()

    try:
        await email_service.send_password_reset_email(email, code, locale=user.locale)
    except Exception:
        logger.exception("Failed to send password reset email for %s", email)


async def verify_code(email: str, code: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("Invalid code")

    await _require_valid_code(user.id, code, db)


async def reset_password(email: str, code: str, new_password: str, db: AsyncSession) -> None:
    # Serialize resets for one account. Besides protecting token_version from
    # a lost update, this makes the reset code truly one-time when two copies
    # of the same request arrive concurrently.
    result = await db.execute(
        select(User).where(User.email == email).with_for_update()
    )
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("Invalid code")

    await _require_valid_code(user.id, code, db)

    user.hashed_password = hash_password(new_password)
    user.token_version += 1
    await _invalidate_reset_tokens(user.id, db)
    await db.commit()
