"""scripts/create_{admin,psychologist}_user.py (PRO-466): invite by email,
print the link — never take a password."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models.invitation import Invitation
from app.models.user import User, UserRole
from app.schemas.invitation import AdminInvitationCreate
from app.services import email_service
from app.services.invitation_service import hash_token
from scripts import staff_invitation_cli


@pytest.fixture(autouse=True)
def cli_session(monkeypatch, db_session: AsyncSession):
    @asynccontextmanager
    async def _session():
        yield db_session

    monkeypatch.setattr(staff_invitation_cli, "async_session", _session)


@pytest.fixture
def sent_emails(monkeypatch) -> list[str]:
    links: list[str] = []

    async def _capture(to: str, invite_url: str, **_kwargs) -> bool:
        links.append(invite_url)
        return True

    monkeypatch.setattr(email_service, "send_invitation_email", _capture)
    return links


def _body(email: str, role: UserRole = UserRole.psychologist) -> AdminInvitationCreate:
    return AdminInvitationCreate(email=email, role=role, locale="kk")


async def test_creates_invitation_without_inviter_and_user(
    db_session: AsyncSession, sent_emails: list[str]
) -> None:
    email = f"{uuid.uuid4()}@example.com"

    sent = await staff_invitation_cli._invite(_body(email, UserRole.admin))

    assert sent.role == UserRole.admin
    assert sent.locale == "kk"
    assert sent.invited_by is None
    assert sent_emails == [sent.invite_url]
    assert await db_session.scalar(select(User).where(User.email == email)) is None


async def _add_pending(db: AsyncSession, email: str, *, role: UserRole, locale: str) -> Invitation:
    invitation = Invitation(
        email=email,
        role=role,
        locale=locale,
        token_hash=hash_token("old-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(invitation)
    await db.flush()
    return invitation


async def test_matching_pending_invitation_gets_its_link_reissued(
    db_session: AsyncSession, sent_emails: list[str]
) -> None:
    email = f"{uuid.uuid4()}@example.com"
    existing = await _add_pending(db_session, email, role=UserRole.psychologist, locale="kk")

    sent = await staff_invitation_cli._invite(_body(email))

    assert sent.id == existing.id
    rows = (await db_session.scalars(select(Invitation).where(Invitation.email == email))).all()
    assert len(rows) == 1
    assert rows[0].token_hash != hash_token("old-token")


@pytest.mark.parametrize(
    ("role", "locale"), [(UserRole.psychologist, "ru"), (UserRole.admin, "kk")], ids=["other_locale", "other_role"]
)
async def test_mismatching_pending_invitation_is_refused_without_replace(
    db_session: AsyncSession, sent_emails: list[str], role: UserRole, locale: str
) -> None:
    email = f"{uuid.uuid4()}@example.com"
    existing = await _add_pending(db_session, email, role=role, locale=locale)

    with pytest.raises(staff_invitation_cli.PendingMismatch):
        await staff_invitation_cli._invite(_body(email))

    await db_session.refresh(existing)
    assert existing.revoked_at is None
    assert existing.token_hash == hash_token("old-token")
    assert sent_emails == []


async def test_replace_revokes_mismatching_invitation_and_invites_anew(
    db_session: AsyncSession, sent_emails: list[str]
) -> None:
    email = f"{uuid.uuid4()}@example.com"
    existing = await _add_pending(db_session, email, role=UserRole.psychologist, locale="ru")

    sent = await staff_invitation_cli._invite(_body(email, UserRole.admin), replace=True)

    assert sent.id != existing.id
    assert sent.role == UserRole.admin
    assert sent.locale == "kk"
    await db_session.refresh(existing)
    assert existing.revoked_at is not None


async def test_verified_account_is_refused(db_session: AsyncSession, sent_emails: list[str]) -> None:
    email = f"{uuid.uuid4()}@example.com"
    db_session.add(User(email=email, hashed_password="x", is_verified=True))
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await staff_invitation_cli._invite(_body(email))

    assert exc_info.value.error_code == "user_exists"
    assert sent_emails == []
