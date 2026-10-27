import asyncio
import threading
import time
from http import HTTPStatus

from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.catalog import key as i18n_key
from app.config import settings
from app.models.invitation import Invitation
from app.models.user import User
from app.services import invitation_service
from app.services.auth_service import create_jwt_token
from app.services.crm import invites

# requests.Session (which google.auth.transport.requests.Request wraps) isn't
# safe for concurrent use from multiple threads. asyncio.to_thread draws from
# a shared thread pool, so a module-level singleton would be reused
# concurrently across those worker threads. A thread-local instance keeps
# each worker thread's session private while still reusing it across calls
# on that same thread.
_thread_local = threading.local()

# How long Google's signing certificates are reused before being fetched
# again. Google rotates them over days and publishes a new key ahead of its
# first use, so an hour never rejects a valid token.
_CERTS_TTL_SECONDS = 60 * 60
# google-auth's own default is 120s — far longer than a login may hang.
_CERTS_FETCH_TIMEOUT_SECONDS = 10


# url -> (monotonic deadline, response). One cache for the process: a fetched
# response is only ever read, so worker threads share it safely, unlike the
# session that fetched it.
_certs_cache: dict[str, tuple[float, object]] = {}


class _CachingRequest:
    """`google.auth` transport that keeps the certificates it has fetched.

    `verify_oauth2_token` downloads them before it even parses the token, on
    every call — so each request to `/auth/google`, garbage included, used to
    cost an outbound HTTPS round trip and a worker thread for its duration.
    Only a successful GET is remembered; a failed one is retried next time."""

    def __init__(self) -> None:
        self._request = google_requests.Request()

    def __call__(self, url: str, method: str = "GET", **kwargs):
        if method != "GET":
            return self._request(url, method=method, **kwargs)
        cached = _certs_cache.get(url)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]
        kwargs.setdefault("timeout", _CERTS_FETCH_TIMEOUT_SECONDS)
        response = self._request(url, method=method, **kwargs)
        if response.status == HTTPStatus.OK:
            _certs_cache[url] = (time.monotonic() + _CERTS_TTL_SECONDS, response)
        return response


def _get_google_request() -> _CachingRequest:
    request = getattr(_thread_local, "request", None)
    if request is None:
        request = _CachingRequest()
        _thread_local.request = request
    return request


def _verify_in_worker(token: str) -> dict:
    # The transport is looked up here, on the worker thread: resolved by the
    # caller it would be the event loop's one, shared by every worker.
    return google_id_token.verify_oauth2_token(token, _get_google_request(), settings.GOOGLE_CLIENT_ID)


async def verify_google_id_token(token: str) -> dict:
    try:
        claims = await asyncio.to_thread(_verify_in_worker, token)
    except (ValueError, google_auth_exceptions.GoogleAuthError) as exc:
        raise ValueError(i18n_key("api_errors", "invalid_google_token", locale="ru")) from exc

    if not claims.get("email_verified"):
        raise ValueError(i18n_key("api_errors", "google_email_not_verified", locale="ru"))

    if "email" not in claims:
        raise ValueError(i18n_key("api_errors", "google_token_missing_email_claim", locale="ru"))

    return claims


async def _lookup_google_user(google_id: str, email: str, db: AsyncSession) -> User | None:
    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()
    if user:
        return user

    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


def _adopt_as_google_verified(user: User, google_id: str, invitation: Invitation | None) -> None:
    if not user.is_verified:
        # An unverified row could have been created by someone else
        # squatting on this email with a password of their choosing —
        # Google's verification of the email is trustworthy, the
        # row's existing password is not. Clear it so that password
        # stops granting access once we adopt the row as verified.
        user.hashed_password = None
        # Only an adopted row takes the invited role: a verified account is
        # never silently promoted, its invitation just stays pending.
        if invitation is not None:
            invitation_service.apply_to_user(user, invitation)
    user.google_id = google_id
    user.is_verified = True


async def login_or_register_google(
    token: str, db: AsyncSession, *, student_invite: str | None = None
) -> tuple[User, str]:
    """Google sign-in. A pending staff invitation on the Google email is
    accepted here as well (PRO-462): a new or adopted account gets the
    invited role instead of `student`. A new student account needs the CRM
    invite link while registration is invite-only (ТЗ §4.4)."""
    claims = await verify_google_id_token(token)
    google_id, email = claims["sub"], claims["email"].strip().lower()

    # Ordered against a concurrent invitation create — see `lock_email`.
    await invitation_service.lock_email(db, email)
    user = await _lookup_google_user(google_id, email, db)
    invitation = await invitation_service.pending_for_email(db, email)

    if user:
        _adopt_as_google_verified(user, google_id, invitation)
        await db.commit()
        await db.refresh(user)
        return user, create_jwt_token(user)

    if invitation is None:
        await invites.require_open_invite(db, student_invite)
    user = User(email=email, hashed_password=None, google_id=google_id, is_verified=True)
    if invitation is not None:
        invitation_service.apply_to_user(user, invitation)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent first-time Google logins for the same brand-new
        # account can both pass the lookups above and both attempt to
        # insert; the loser hits a unique-constraint violation here instead
        # of finding the row, so recover by re-fetching the winner's row
        # rather than surfacing a 500 for what the user experiences as an
        # ordinary login. The same violation is also reachable when the race
        # is against a *password* signup on this email instead of a second
        # Google login — apply the same squatting-adoption logic as the
        # `if user:` branch above, or an attacker's password set moments
        # earlier would still grant access to the row Google just verified.
        # The rollback dropped the invitation lock too — look it up again.
        await db.rollback()
        await invitation_service.lock_email(db, email)
        user = await _lookup_google_user(google_id, email, db)
        if user is None:
            raise
        invitation = await invitation_service.pending_for_email(db, email)
        _adopt_as_google_verified(user, google_id, invitation)
        await db.commit()
        await db.refresh(user)
        return user, create_jwt_token(user)

    await db.refresh(user)
    return user, create_jwt_token(user)
