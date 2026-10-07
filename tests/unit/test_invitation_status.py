"""Derived invitation status (PRO-459): no stored status column, the
timestamps decide — accepted > revoked > expired > pending."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.invitation import Invitation, InvitationStatus
from app.models.user import UserRole

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(hours=1)
FUTURE = NOW + timedelta(days=7)


def _invitation(
    *,
    expires_at: datetime = FUTURE,
    accepted_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> Invitation:
    return Invitation(
        email="psy@example.com",
        role=UserRole.psychologist,
        locale="ru",
        token_hash="0" * 64,
        expires_at=expires_at,
        accepted_at=accepted_at,
        revoked_at=revoked_at,
    )


@pytest.mark.parametrize(
    ("invitation", "expected"),
    [
        (_invitation(), InvitationStatus.pending),
        (_invitation(expires_at=PAST), InvitationStatus.expired),
        (_invitation(expires_at=NOW), InvitationStatus.expired),
        (_invitation(revoked_at=PAST), InvitationStatus.revoked),
        (_invitation(accepted_at=PAST), InvitationStatus.accepted),
        # Terminal states win over expiry: an invite accepted or revoked
        # before its deadline keeps that status after the deadline passes.
        (_invitation(expires_at=PAST, accepted_at=PAST), InvitationStatus.accepted),
        (_invitation(expires_at=PAST, revoked_at=PAST), InvitationStatus.revoked),
        (_invitation(accepted_at=PAST, revoked_at=PAST), InvitationStatus.accepted),
    ],
    ids=[
        "pending",
        "expired",
        "expired_at_deadline",
        "revoked",
        "accepted",
        "accepted_then_deadline_passed",
        "revoked_then_deadline_passed",
        "accepted_wins_over_revoked",
    ],
)
def test_status_at(invitation: Invitation, expected: InvitationStatus) -> None:
    assert invitation.status_at(NOW) is expected


def test_status_uses_current_time() -> None:
    now = datetime.now(timezone.utc)
    assert _invitation(expires_at=now + timedelta(days=1)).status is InvitationStatus.pending
    assert _invitation(expires_at=now - timedelta(seconds=1)).status is InvitationStatus.expired
