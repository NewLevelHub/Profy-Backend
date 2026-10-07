"""Staff email invitations: admin side (PRO-460) and accepting (PRO-462).

Contract: docs/frontend-admin-invitations-api-contract.md. No `users` row
exists until the invitation is accepted — by password here, by a Google
login on the invited email (`oauth_service`), or by confirming the code of
an unverified registration on that email (`auth_service.verify_email`).

A link is found by the SHA-256 of its token. The token itself is also kept,
encrypted (Fernet, key derived from `SECRET_KEY`), while the invitation is
open — so the admin can copy the link again (`invitation_link`).
"""

import asyncio
import base64
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from email_validator import EmailUndeliverableError, validate_email
from fastapi import status
from sqlalchemy import exists, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import AppError
from app.i18n.catalog import key as i18n_key
from app.models.invitation import Invitation, InvitationEmailStatus, InvitationStatus
from app.models.user import User
from app.schemas.invitation import (
    AcceptInvitationRequest,
    AdminInvitationCreate,
    AdminInvitationItem,
    AdminInvitationLink,
    AdminInvitationListResponse,
    AdminInvitationSent,
    InvitationInviter,
    InvitationPreview,
)
from app.services import auth_service, email_service
from app.services.token_utils import hash_code

logger = logging.getLogger(__name__)

# The MX lookup on create; past this the address is let through.
_DELIVERABILITY_TIMEOUT_SECONDS = 5

# Error code for an operation that needs an open invitation but got a closed one.
_CLOSED_STATUS_ERRORS: dict[InvitationStatus, str] = {
    InvitationStatus.accepted: "invitation_used",
    InvitationStatus.revoked: "invitation_revoked",
    InvitationStatus.expired: "invitation_expired",
}

# Delivery events never move the status back: a "delayed" arriving after
# "delivered", or anything after a bounce, is ignored.
_EMAIL_STATUS_RANK: dict[InvitationEmailStatus, int] = {
    InvitationEmailStatus.sent: 0,
    InvitationEmailStatus.delayed: 1,
    InvitationEmailStatus.delivered: 2,
    InvitationEmailStatus.bounced: 3,
    InvitationEmailStatus.complained: 3,
    InvitationEmailStatus.failed: 3,
}


def invitation_error(status_code: int, error_code: str) -> AppError:
    return AppError(
        status_code=status_code,
        error_code=error_code,
        detail=i18n_key("api_errors", error_code),
    )


def hash_token(token: str) -> str:
    return hash_code(token)


def build_invite_url(token: str) -> str:
    return email_service.frontend_url(f"/invite?token={token}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@lru_cache(maxsize=1)
def _link_cipher() -> Fernet:
    # A key of its own, derived from SECRET_KEY: the JWT signing key is
    # not used directly as an encryption key.
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"profile:invitation-link"
    ).derive(settings.SECRET_KEY.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def _issue_token(invitation: Invitation, now: datetime) -> str:
    """New link for `invitation`: replaces the hash, so any older link stops
    resolving, and restarts the TTL."""
    token = secrets.token_urlsafe(32)
    invitation.token_hash = hash_token(token)
    invitation.token_ciphertext = _link_cipher().encrypt(token.encode("ascii")).decode("ascii")
    invitation.expires_at = now + timedelta(hours=settings.INVITATION_TTL_HOURS)
    return token


def _decrypt_token(invitation: Invitation) -> str | None:
    """None when the link can't be recovered: created before links were
    kept, or `SECRET_KEY` changed since — a resend issues a new one."""
    if invitation.token_ciphertext is None:
        return None
    try:
        token = _link_cipher().decrypt(invitation.token_ciphertext.encode("ascii")).decode("ascii")
    except InvalidToken:
        return None
    if hash_token(token) != invitation.token_hash:
        logger.error("invitation %s: stored link does not match its hash", invitation.id)
        return None
    return token


async def ensure_deliverable(email: str) -> None:
    """Reject a domain that can't receive mail (no MX / A record, null MX):
    a typo or a made-up domain must not end up as "email sent". A DNS
    timeout lets the address through."""
    if not settings.INVITATION_CHECK_DELIVERABILITY:
        return
    try:
        await asyncio.to_thread(
            validate_email,
            email,
            check_deliverability=True,
            timeout=_DELIVERABILITY_TIMEOUT_SECONDS,
        )
    except EmailUndeliverableError:
        raise invitation_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "invitation_email_undeliverable"
        ) from None


async def _lock_email(db: AsyncSession, email: str) -> None:
    """Serialize create/resend per email until commit, so two concurrent
    requests can't both pass the "no pending invitation" check."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"invitation:{email}"}
    )


async def ensure_no_verified_user(db: AsyncSession, email: str) -> None:
    """An unverified account doesn't block — accepting adopts it (PRO-462)."""
    has_user = await db.scalar(
        select(exists().where(User.email == email, User.is_verified.is_(True)))
    )
    if has_user:
        raise invitation_error(status.HTTP_409_CONFLICT, "user_exists")


async def _ensure_no_other_pending(
    db: AsyncSession, email: str, now: datetime, *, exclude_id: uuid.UUID | None = None
) -> None:
    conditions = [Invitation.email == email, Invitation.status_filter(InvitationStatus.pending, now)]
    if exclude_id is not None:
        conditions.append(Invitation.id != exclude_id)
    if await db.scalar(select(exists().where(*conditions))):
        raise invitation_error(status.HTTP_409_CONFLICT, "invitation_pending")


async def _get_for_update(db: AsyncSession, invitation_id: uuid.UUID) -> Invitation:
    invitation = await db.scalar(
        select(Invitation).where(Invitation.id == invitation_id).with_for_update()
    )
    if invitation is None:
        raise invitation_error(status.HTTP_404_NOT_FOUND, "invitation_not_found")
    return invitation


async def _send_email(invitation: Invitation, token: str, now: datetime) -> None:
    """Send, and record the outcome on `invitation` (the caller commits).
    A failure leaves the link valid — the admin hands it over by hand."""
    try:
        message_id = await email_service.send_invitation_email(
            invitation.email,
            build_invite_url(token),
            role=invitation.role,
            locale=invitation.locale,
        )
    except Exception:
        # email_service has logged the provider error.
        message_id = None
    invitation.email_message_id = message_id or None
    invitation.email_status = (
        InvitationEmailStatus.sent if message_id is not None else InvitationEmailStatus.failed
    )
    invitation.email_status_at = now


def _item(invitation: Invitation, inviter_email: str | None, now: datetime) -> AdminInvitationItem:
    inviter = (
        InvitationInviter(id=invitation.invited_by, email=inviter_email)
        if invitation.invited_by is not None and inviter_email is not None
        else None
    )
    return AdminInvitationItem(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        locale=invitation.locale,
        status=invitation.status_at(now),
        invited_by=inviter,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        email_status=invitation.email_status,
    )


async def _inviter_email(db: AsyncSession, invitation: Invitation) -> str | None:
    if invitation.invited_by is None:
        return None
    return await db.scalar(select(User.email).where(User.id == invitation.invited_by))


async def _sent(
    db: AsyncSession, invitation: Invitation, token: str, now: datetime
) -> AdminInvitationSent:
    """Called once the new token is committed: the email only ever carries a
    link that already works, and the provider call holds no lock."""
    await _send_email(invitation, token, now)
    await db.commit()
    item = _item(invitation, await _inviter_email(db, invitation), now)
    return AdminInvitationSent(
        **item.model_dump(),
        invite_url=build_invite_url(token),
        email_sent=invitation.email_status == InvitationEmailStatus.sent,
    )


async def create_invitation(
    db: AsyncSession,
    body: AdminInvitationCreate,
    *,
    inviter: User | None,
    check_deliverability: bool = True,
) -> AdminInvitationSent:
    """`inviter` is None for the CLI scripts (`scripts/create_*_user.py`),
    which also skip the mail-domain check: they print the link."""
    # Before the lock: a DNS lookup must not hold other requests up.
    if check_deliverability:
        await ensure_deliverable(body.email)
    await _lock_email(db, body.email)
    await ensure_no_verified_user(db, body.email)
    now = _now()
    await _ensure_no_other_pending(db, body.email, now)

    invitation = Invitation(
        email=body.email,
        role=body.role,
        locale=body.locale,
        invited_by=inviter.id if inviter else None,
    )
    token = _issue_token(invitation, now)
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return await _sent(db, invitation, token, now)


async def list_invitations(
    db: AsyncSession,
    *,
    page: int,
    limit: int,
    status_filter: InvitationStatus | None = None,
    search: str | None = None,
) -> AdminInvitationListResponse:
    now = _now()
    filters = []
    if status_filter is not None:
        filters.append(Invitation.status_filter(status_filter, now))
    if search and search.strip():
        filters.append(Invitation.email.ilike(f"%{search.strip()}%"))

    total = await db.scalar(select(func.count()).select_from(Invitation).where(*filters))
    rows = await db.execute(
        select(Invitation, User.email)
        .outerjoin(User, User.id == Invitation.invited_by)
        .where(*filters)
        .order_by(Invitation.created_at.desc(), Invitation.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return AdminInvitationListResponse(
        items=[_item(invitation, inviter_email, now) for invitation, inviter_email in rows.all()],
        total=total or 0,
        page=page,
        limit=limit,
    )


async def resend_invitation(db: AsyncSession, invitation_id: uuid.UUID) -> AdminInvitationSent:
    """`pending` / `expired` only: same row, new token and TTL, new email."""
    invitation = await _get_for_update(db, invitation_id)
    now = _now()
    current = invitation.status_at(now)
    if current in (InvitationStatus.accepted, InvitationStatus.revoked):
        raise invitation_error(status.HTTP_400_BAD_REQUEST, _CLOSED_STATUS_ERRORS[current])

    await _lock_email(db, invitation.email)
    await ensure_no_verified_user(db, invitation.email)
    # An expired row coming back to life must not duplicate a newer pending one.
    await _ensure_no_other_pending(db, invitation.email, now, exclude_id=invitation.id)

    token = _issue_token(invitation, now)
    await db.commit()
    return await _sent(db, invitation, token, now)


async def revoke_invitation(db: AsyncSession, invitation_id: uuid.UUID) -> AdminInvitationItem:
    invitation = await _get_for_update(db, invitation_id)
    now = _now()
    current = invitation.status_at(now)
    if current != InvitationStatus.pending:
        raise invitation_error(status.HTTP_400_BAD_REQUEST, _CLOSED_STATUS_ERRORS[current])

    invitation.revoked_at = now
    invitation.token_ciphertext = None
    await db.commit()
    return _item(invitation, await _inviter_email(db, invitation), now)


async def invitation_link(db: AsyncSession, invitation_id: uuid.UUID) -> AdminInvitationLink:
    """The current link of a pending invitation — the one in the latest email."""
    invitation = await db.scalar(select(Invitation).where(Invitation.id == invitation_id))
    if invitation is None:
        raise invitation_error(status.HTTP_404_NOT_FOUND, "invitation_not_found")
    current = invitation.status_at(_now())
    if current != InvitationStatus.pending:
        raise invitation_error(status.HTTP_400_BAD_REQUEST, _CLOSED_STATUS_ERRORS[current])
    token = _decrypt_token(invitation)
    if token is None:
        raise invitation_error(status.HTTP_409_CONFLICT, "invitation_link_unavailable")
    return AdminInvitationLink(invite_url=build_invite_url(token), expires_at=invitation.expires_at)


async def record_email_event(
    db: AsyncSession, message_id: str, email_status: InvitationEmailStatus, at: datetime
) -> bool:
    """Resend webhook: apply a delivery event to the invitation whose latest
    email it is. False when none matches — another kind of email, or one
    already replaced by a resend."""
    invitation = await db.scalar(
        select(Invitation).where(Invitation.email_message_id == message_id).with_for_update()
    )
    if invitation is None:
        return False
    current = invitation.email_status
    if current is None or _EMAIL_STATUS_RANK[email_status] >= _EMAIL_STATUS_RANK[current]:
        invitation.email_status = email_status
        invitation.email_status_at = at
    await db.commit()
    return True


# ── accepting (public) ──────────────────────────────────────────────────────


def apply_to_user(user: User, invitation: Invitation) -> None:
    """Turn `user` into the invited staff member and close the invitation."""
    user.role = invitation.role
    user.locale = invitation.locale
    user.is_verified = True
    invitation.accepted_at = _now()
    invitation.token_ciphertext = None


async def has_pending(db: AsyncSession, email: str) -> bool:
    """Login / registration on an invited email: the account is made from
    the emailed link, so the person is sent back to it."""
    return bool(
        await db.scalar(
            select(
                exists().where(
                    Invitation.email == email,
                    Invitation.status_filter(InvitationStatus.pending, _now()),
                )
            )
        )
    )


async def pending_for_email(db: AsyncSession, email: str) -> Invitation | None:
    """The open invitation for `email`, row-locked (Google login and email
    confirmation paths)."""
    return await db.scalar(
        select(Invitation)
        .where(Invitation.email == email, Invitation.status_filter(InvitationStatus.pending, _now()))
        .order_by(Invitation.created_at.desc())
        .limit(1)
        .with_for_update()
    )


async def _open_invitation_by_token(
    db: AsyncSession, token: str, *, for_update: bool = False
) -> Invitation:
    query = select(Invitation).where(Invitation.token_hash == hash_token(token))
    if for_update:
        query = query.with_for_update()
    invitation = await db.scalar(query)
    if invitation is None:
        raise invitation_error(status.HTTP_400_BAD_REQUEST, "invitation_invalid")
    current = invitation.status_at(_now())
    if current == InvitationStatus.accepted and not await _account_exists(db, invitation.email):
        # The account made from it has been deleted: "already accepted — sign
        # in" would send the person to a login that can't work.
        raise invitation_error(status.HTTP_400_BAD_REQUEST, "invitation_invalid")
    if current != InvitationStatus.pending:
        raise invitation_error(status.HTTP_400_BAD_REQUEST, _CLOSED_STATUS_ERRORS[current])
    return invitation


async def _account_exists(db: AsyncSession, email: str) -> bool:
    return bool(await db.scalar(select(exists().where(User.email == email))))


async def preview_invitation(db: AsyncSession, token: str) -> InvitationPreview:
    invitation = await _open_invitation_by_token(db, token)
    await ensure_no_verified_user(db, invitation.email)
    return InvitationPreview(
        email=invitation.email,
        role=invitation.role,
        locale=invitation.locale,
        expires_at=invitation.expires_at,
    )


async def accept_invitation(
    db: AsyncSession, body: AcceptInvitationRequest, *, retry_on_conflict: bool = True
) -> tuple[User, str]:
    """Create (or take over) the invitee's account and return a JWT.

    The invitation row is locked, so two concurrent accepts of one token
    serialize: the second sees `accepted` and gets `invitation_used`."""
    invitation = await _open_invitation_by_token(db, body.token, for_update=True)
    user = await db.scalar(select(User).where(User.email == invitation.email).with_for_update())
    if user is not None and user.is_verified:
        raise invitation_error(status.HTTP_409_CONFLICT, "user_exists")

    hashed_password = auth_service.hash_password(body.password)
    if user is None:
        user = User(email=invitation.email, hashed_password=hashed_password)
        db.add(user)
    else:
        # Registered on this email after the invite but never verified: the
        # invitee takes the row over, and the stranger's password and any
        # tokens stop working.
        user.hashed_password = hashed_password
        user.token_version += 1
    apply_to_user(user, invitation)

    try:
        await db.commit()
    except IntegrityError:
        # A registration on this email committed between the lookup and the
        # insert. Retry once — that row is now found and taken over.
        await db.rollback()
        if not retry_on_conflict:
            raise
        return await accept_invitation(db, body, retry_on_conflict=False)
    await db.refresh(user)
    return user, auth_service.create_jwt_token(user)
