import asyncio

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.services.auth_service import create_jwt_token

_google_request = google_requests.Request()


async def verify_google_id_token(token: str) -> dict:
    try:
        claims = await asyncio.to_thread(
            google_id_token.verify_oauth2_token,
            token,
            _google_request,
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise ValueError("Invalid Google token") from exc

    if not claims.get("email_verified"):
        raise ValueError("Google email not verified")

    return claims


async def login_or_register_google(token: str, db: AsyncSession) -> tuple[User, str]:
    claims = await verify_google_id_token(token)
    google_id, email = claims["sub"], claims["email"].strip().lower()

    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if not user:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            if not user.is_verified:
                # An unverified row could have been created by someone else
                # squatting on this email with a password of their choosing —
                # Google's verification of the email is trustworthy, the
                # row's existing password is not. Clear it so that password
                # stops granting access once we adopt the row as verified.
                user.hashed_password = None
            user.google_id = google_id
            user.is_verified = True
        else:
            user = User(
                email=email,
                hashed_password=None,
                google_id=google_id,
                is_verified=True,
            )
            db.add(user)
        await db.commit()
        await db.refresh(user)

    return user, create_jwt_token(user.id)
