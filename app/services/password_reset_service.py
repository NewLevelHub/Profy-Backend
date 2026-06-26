import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services import email_service
from app.services.auth_service import hash_password
from app.services.token_utils import generate_code, hash_code


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
    result = await db.execute(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
        .order_by(PasswordResetToken.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def initiate_reset(email: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or user.hashed_password is None:
        return

    await _invalidate_reset_tokens(user.id, db)

    code = generate_code()
    token = PasswordResetToken(
        user_id=user.id,
        code_hash=hash_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(token)
    await db.commit()

    await email_service.send_password_reset_email(email, code)


async def verify_code(email: str, code: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("Invalid code")

    token = await _get_active_token(user.id, db)
    if not token:
        raise ValueError("Invalid code")

    now = datetime.now(timezone.utc)
    expires = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    if now > expires:
        raise ValueError("Code expired")

    if token.code_hash != hash_code(code):
        raise ValueError("Invalid code")


async def reset_password(email: str, code: str, new_password: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("Invalid code")

    token = await _get_active_token(user.id, db)
    if not token:
        raise ValueError("Invalid code")

    now = datetime.now(timezone.utc)
    expires = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    if now > expires:
        raise ValueError("Code expired")

    if token.code_hash != hash_code(code):
        raise ValueError("Invalid code")

    user.hashed_password = hash_password(new_password)
    await _invalidate_reset_tokens(user.id, db)
    await db.commit()
