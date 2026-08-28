"""A failing Resend send must not fail registration/reset — the DB write
already succeeded by the time the email is attempted, so the email step is
best-effort. `email_service.send_*` is monkeypatched directly on the shared
module object, same pattern used in test_report_narrative_service.py."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_verification import EmailVerificationToken
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services import auth_service, email_service, password_reset_service


async def _raise(*args, **kwargs) -> None:
    raise RuntimeError("Resend: daily quota exceeded")


async def test_register_succeeds_even_if_verification_email_fails(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(email_service, "send_verification_email", _raise)

    email = f"{uuid.uuid4()}@example.test"
    response = await auth_service.register(email, "Testpass123!", db_session)

    assert response.email == email

    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    assert user.is_verified is False

    token = (
        await db_session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
        )
    ).scalar_one_or_none()
    assert token is not None


async def test_resend_verification_succeeds_even_if_email_fails(
    db_session: AsyncSession, monkeypatch
) -> None:
    email = f"{uuid.uuid4()}@example.test"
    user = User(
        email=email,
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=False,
    )
    db_session.add(user)
    await db_session.commit()

    monkeypatch.setattr(email_service, "send_verification_email", _raise)

    await auth_service.resend_verification(email, db_session)

    token = (
        await db_session.execute(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.user_id == user.id)
            .order_by(EmailVerificationToken.created_at.desc())
        )
    ).scalars().first()
    assert token is not None
    assert token.used_at is None


async def test_initiate_reset_succeeds_even_if_email_fails(
    db_session: AsyncSession, monkeypatch
) -> None:
    email = f"{uuid.uuid4()}@example.test"
    user = User(
        email=email,
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    monkeypatch.setattr(email_service, "send_password_reset_email", _raise)

    await password_reset_service.initiate_reset(email, db_session)

    token = (
        await db_session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
    ).scalar_one_or_none()
    assert token is not None
