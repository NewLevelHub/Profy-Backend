"""Shared body of `create_admin_user.py` / `create_psychologist_user.py`
(PRO-466): invite a staff member by email and print the one-time link.

No password goes through argv or shell history — the invitee sets it when
accepting the link (or signs in with Google). The rules are the admin
panel's (`app/services/invitation_service.py`): a verified account on the
email is refused; an already pending invitation gets its link reissued
(the old link stops working), so a lost link can be recovered before any
admin exists to press "resend".
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import async_session  # noqa: E402
from app.errors import AppError  # noqa: E402
from app.i18n import DEFAULT_LOCALE, KNOWN_LOCALES  # noqa: E402
from app.models.user import UserRole  # noqa: E402
from app.schemas.invitation import AdminInvitationCreate, AdminInvitationSent  # noqa: E402
from app.services import invitation_service  # noqa: E402


def _parse_args(role: UserRole) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Invite a staff member ({role.value}) by email and print the invitation link."
    )
    parser.add_argument("email")
    parser.add_argument(
        "--locale",
        choices=KNOWN_LOCALES,
        default=DEFAULT_LOCALE,
        help="language of the email and of the new account (default: %(default)s)",
    )
    return parser.parse_args()


async def _invite(body: AdminInvitationCreate) -> AdminInvitationSent:
    async with async_session() as db:
        try:
            return await invitation_service.create_invitation(db, body, inviter=None)
        except AppError as exc:
            if exc.error_code != "invitation_pending":
                raise
        # Nothing was written before the refusal; the same transaction goes on.
        pending = await invitation_service.pending_for_email(db, body.email)
        if pending is None:  # accepted or revoked in the meantime — just retry
            return await invitation_service.create_invitation(db, body, inviter=None)
        print("A pending invitation already exists — reissuing its link (the old one stops working).")
        return await invitation_service.resend_invitation(db, pending.id)


def _email_status(sent: AdminInvitationSent) -> str:
    if not settings.RESEND_API_KEY:
        return "not sent (RESEND_API_KEY is empty) — hand the link over yourself"
    return "sent" if sent.email_sent else "FAILED — hand the link over yourself"


def run(role: UserRole) -> None:
    args = _parse_args(role)
    try:
        body = AdminInvitationCreate(email=args.email, role=role, locale=args.locale)
        sent = asyncio.run(_invite(body))
    except ValidationError as exc:
        sys.exit(f"Invalid input: {exc.errors()[0]['msg']}")
    except AppError as exc:
        sys.exit(f"Refused: {exc.detail} ({exc.error_code})")

    print(f"Invitation for {sent.email} ({sent.role.value}, {sent.locale}), valid until {sent.expires_at:%Y-%m-%d %H:%M %Z}:")
    print(f"  {sent.invite_url}")
    print(f"Email: {_email_status(sent)}")
