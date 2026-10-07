"""Shared body of `create_admin_user.py` / `create_psychologist_user.py`
(PRO-466): invite a staff member by email and print the one-time link.

No password goes through argv or shell history — the invitee sets it when
accepting the link (or signs in with Google). The rules are the admin
panel's (`app/services/invitation_service.py`): a verified account on the
email is refused. An already pending invitation with the same role and
locale gets its link reissued (the old link stops working), so a lost link
can be recovered before any admin exists to press "resend". A pending one
with a different role/locale is refused unless `--replace` is given, which
revokes it and invites anew — never silently hand out the old role.
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
    parser.add_argument(
        "--replace",
        action="store_true",
        help="revoke a pending invitation with a different role/locale and invite anew",
    )
    return parser.parse_args()


class PendingMismatch(Exception):
    """A pending invitation exists with another role/locale and no --replace."""


async def _invite(body: AdminInvitationCreate, *, replace: bool = False) -> AdminInvitationSent:
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
        if pending.role == body.role and pending.locale == body.locale:
            print("A pending invitation already exists — reissuing its link (the old one stops working).")
            return await invitation_service.resend_invitation(db, pending.id)
        current = f"{pending.role.value}/{pending.locale}"
        if not replace:
            raise PendingMismatch(
                f"A pending {current} invitation already exists for {body.email}. "
                f"Rerun with --replace to revoke it and invite as {body.role.value}/{body.locale}."
            )
        print(f"Revoking the pending {current} invitation.")
        await invitation_service.revoke_invitation(db, pending.id)
        return await invitation_service.create_invitation(db, body, inviter=None)


def _email_status(sent: AdminInvitationSent) -> str:
    if sent.email_sent:
        return "sent"
    if not settings.RESEND_API_KEY:
        return "not sent (RESEND_API_KEY is empty) — hand the link over yourself"
    return "FAILED — hand the link over yourself"


def run(role: UserRole) -> None:
    args = _parse_args(role)
    try:
        body = AdminInvitationCreate(email=args.email, role=role, locale=args.locale)
        sent = asyncio.run(_invite(body, replace=args.replace))
    except ValidationError as exc:
        sys.exit(f"Invalid input: {exc.errors()[0]['msg']}")
    except AppError as exc:
        sys.exit(f"Refused: {exc.detail} ({exc.error_code})")
    except PendingMismatch as exc:
        sys.exit(f"Refused: {exc}")

    print(f"Invitation for {sent.email} ({sent.role.value}, {sent.locale}), valid until {sent.expires_at:%Y-%m-%d %H:%M %Z}:")
    print(f"  {sent.invite_url}")
    print(f"Email: {_email_status(sent)}")
