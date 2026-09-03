import asyncio
import threading

from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.services.auth_service import create_jwt_token

# requests.Session (which google.auth.transport.requests.Request wraps) isn't
# safe for concurrent use from multiple threads. asyncio.to_thread draws from
# a shared thread pool, so a module-level singleton would be reused
# concurrently across those worker threads. A thread-local instance keeps
# each worker thread's session private while still reusing it across calls
# on that same thread.
_thread_local = threading.local()


def _get_google_request() -> google_requests.Request:
    request = getattr(_thread_local, "request", None)
    if request is None:
        request = google_requests.Request()
        _thread_local.request = request
    return request


async def verify_google_id_token(token: str) -> dict:
    try:
        claims = await asyncio.to_thread(
            google_id_token.verify_oauth2_token,
            token,
            _get_google_request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except (ValueError, google_auth_exceptions.GoogleAuthError) as exc:
        raise ValueError("Invalid Google token") from exc

    if not claims.get("email_verified"):
        raise ValueError("Google email not verified")

    if "email" not in claims:
        raise ValueError("Google token missing email claim")

    return claims


async def _lookup_google_user(google_id: str, email: str, db: AsyncSession) -> User | None:
    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()
    if user:
        return user

    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def login_or_register_google(token: str, db: AsyncSession) -> tuple[User, str]:
    claims = await verify_google_id_token(token)
    google_id, email = claims["sub"], claims["email"].strip().lower()

    user = await _lookup_google_user(google_id, email, db)

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
        await db.commit()
        await db.refresh(user)
        return user, create_jwt_token(user.id)

    user = User(email=email, hashed_password=None, google_id=google_id, is_verified=True)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent first-time Google logins for the same brand-new
        # account can both pass the lookups above and both attempt to
        # insert; the loser hits a unique-constraint violation here instead
        # of finding the row, so recover by re-fetching the winner's row
        # rather than surfacing a 500 for what the user experiences as an
        # ordinary login.
        await db.rollback()
        user = await _lookup_google_user(google_id, email, db)
        if user is None:
            raise
        return user, create_jwt_token(user.id)

    await db.refresh(user)
    return user, create_jwt_token(user.id)
