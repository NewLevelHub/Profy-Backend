"""Accepting staff invitations (PRO-462) — public endpoints and Google login,
against docs/frontend-admin-invitations-api-contract.md §4–§5."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine
from app.errors import AppError
from app.models.invitation import Invitation, InvitationStatus
from app.models.user import User, UserRole
from app.schemas.invitation import AcceptInvitationRequest
from app.services import auth_service, email_service, invitation_service, oauth_service
from app.services.invitation_service import hash_token
from app.services.oauth_service import google_id_token

PREVIEW_URL = "/api/v1/auth/invitations/{token}"
ACCEPT_URL = "/api/v1/auth/invitations/accept"
PASSWORD = "Invited123"


def _email() -> str:
    return f"{uuid.uuid4()}@example.com"


async def _add_invitation(
    db: AsyncSession,
    email: str,
    *,
    role: UserRole = UserRole.psychologist,
    locale: str = "kk",
    expires_in: timedelta = timedelta(hours=72),
    accepted: bool = False,
    revoked: bool = False,
) -> tuple[Invitation, str]:
    token = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    invitation = Invitation(
        email=email,
        role=role,
        locale=locale,
        token_hash=hash_token(token),
        expires_at=now + expires_in,
        accepted_at=now if accepted else None,
        revoked_at=now if revoked else None,
    )
    db.add(invitation)
    await db.flush()
    return invitation, token


async def _add_user(db: AsyncSession, email: str, *, is_verified: bool, password: str = "Stranger123") -> User:
    user = User(email=email, hashed_password=auth_service.hash_password(password), is_verified=is_verified)
    db.add(user)
    await db.flush()
    return user


def _mock_google(monkeypatch, email: str) -> None:
    sub = str(uuid.uuid4())
    monkeypatch.setattr(
        google_id_token,
        "verify_oauth2_token",
        lambda *a, **kw: {"sub": sub, "email": email, "email_verified": True},
    )


# ── end to end ──────────────────────────────────────────────────────────────


async def test_invite_preview_accept_and_use_the_account(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, monkeypatch
) -> None:
    links: list[str] = []

    async def _capture(to: str, invite_url: str, **_kwargs) -> bool:
        links.append(invite_url)
        return True

    monkeypatch.setattr(email_service, "send_invitation_email", _capture)
    email = _email()
    created = await client.post(
        "/api/v1/admin/invitations",
        json={"email": email, "role": "psychologist", "locale": "kk"},
        headers=admin_headers,
    )
    assert created.status_code == 201
    token = parse_qs(urlparse(links[0]).query)["token"][0]

    preview = await client.get(PREVIEW_URL.format(token=token))
    assert preview.status_code == 200
    assert preview.json()["email"] == email
    assert preview.json()["role"] == "psychologist"
    assert preview.json()["locale"] == "kk"

    accepted = await client.post(ACCEPT_URL, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["user"]["email"] == email
    assert body["user"]["role"] == "psychologist"
    assert body["user"]["locale"] == "kk"

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["role"] == "psychologist"
    assert me.json()["is_verified"] is True

    invitation = await db_session.scalar(select(Invitation).where(Invitation.email == email))
    assert invitation.status_at(datetime.now(timezone.utc)) is InvitationStatus.accepted

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200

    again = await client.post(ACCEPT_URL, json={"token": token, "password": PASSWORD})
    assert again.status_code == 400
    assert again.json()["error_code"] == "invitation_used"


async def test_login_before_accepting_is_401(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    email = _email()
    await _add_invitation(db_session, email)

    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

    assert response.status_code == 401


# ── token states ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("state", "error_code"),
    [
        ({"expires_in": timedelta(hours=-1)}, "invitation_expired"),
        ({"revoked": True}, "invitation_revoked"),
        ({"accepted": True}, "invitation_used"),
        (None, "invitation_invalid"),
    ],
    ids=["expired", "revoked", "used", "unknown"],
)
async def test_closed_or_unknown_token_is_400_with_code(
    client: httpx.AsyncClient, db_session: AsyncSession, state: dict | None, error_code: str
) -> None:
    token = uuid.uuid4().hex
    if state is not None:
        _, token = await _add_invitation(db_session, _email(), **state)

    preview = await client.get(PREVIEW_URL.format(token=token))
    accept = await client.post(ACCEPT_URL, json={"token": token, "password": PASSWORD})

    for response in (preview, accept):
        assert response.status_code == 400
        assert response.json()["error_code"] == error_code


async def test_resend_invalidates_the_old_link(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, monkeypatch
) -> None:
    async def _noop(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr(email_service, "send_invitation_email", _noop)
    invitation, old_token = await _add_invitation(db_session, _email())

    resent = await client.post(f"/api/v1/admin/invitations/{invitation.id}/resend", headers=admin_headers)
    new_token = parse_qs(urlparse(resent.json()["invite_url"]).query)["token"][0]

    old = await client.get(PREVIEW_URL.format(token=old_token))
    new = await client.get(PREVIEW_URL.format(token=new_token))
    assert old.status_code == 400
    assert old.json()["error_code"] == "invitation_invalid"
    assert new.status_code == 200


@pytest.mark.parametrize(
    ("password", "accept_language", "message"),
    [
        ("Ab1", "ru", "Пароль должен быть не короче 8 символов"),
        ("Ab1", "kk", "Құпиясөз кемінде 8 таңбадан тұруы керек"),
        ("onlyletters", "kk", "Құпиясөзде кемінде бір цифр болуы керек"),
    ],
    ids=["short_ru", "short_kk", "no_digit_kk"],
)
async def test_weak_password_is_422_with_localized_message(
    client: httpx.AsyncClient, db_session: AsyncSession, password: str, accept_language: str, message: str
) -> None:
    _, token = await _add_invitation(db_session, _email())

    response = await client.post(
        ACCEPT_URL, json={"token": token, "password": password}, headers={"Accept-Language": accept_language}
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == message


# ── existing accounts on the invited email ─────────────────────────────────


async def test_unverified_account_is_taken_over(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    email = _email()
    _, token = await _add_invitation(db_session, email, role=UserRole.admin, locale="kk")
    squatter = await _add_user(db_session, email, is_verified=False, password="Stranger123")
    old_version = squatter.token_version

    response = await client.post(ACCEPT_URL, json={"token": token, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(squatter.id)
    await db_session.refresh(squatter)
    assert squatter.role == UserRole.admin
    assert squatter.locale == "kk"
    assert squatter.is_verified is True
    assert squatter.token_version == old_version + 1
    assert auth_service.verify_password(PASSWORD, squatter.hashed_password)
    assert not auth_service.verify_password("Stranger123", squatter.hashed_password)


async def test_verified_account_is_409(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    email = _email()
    _, token = await _add_invitation(db_session, email)
    await _add_user(db_session, email, is_verified=True)

    preview = await client.get(PREVIEW_URL.format(token=token))
    accept = await client.post(ACCEPT_URL, json={"token": token, "password": PASSWORD})

    for response in (preview, accept):
        assert response.status_code == 409
        assert response.json()["error_code"] == "user_exists"


# ── concurrency ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("with_unverified_account", [False, True], ids=["new_account", "takeover"])
async def test_two_concurrent_accepts_only_one_wins(
    monkeypatch: pytest.MonkeyPatch, with_unverified_account: bool
) -> None:
    """Real commits on two connections — the shared test session can't
    show row-lock contention. The loser must see the invitation as used
    (the invitation row lock), not trip over the winner's account."""
    email = _email()
    token = uuid.uuid4().hex
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        if with_unverified_account:
            setup.add(User(email=email, hashed_password="x", is_verified=False))
        setup.add(
            Invitation(
                email=email,
                role=UserRole.psychologist,
                locale="ru",
                token_hash=hash_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        await setup.commit()

    # Hold each request right after it read the invitation, until the other
    # one has read it too (or 0.5s passed). With the row lock the second read
    # waits for the first commit, so the barrier times out and the requests
    # run one after another; without it both would pass the "pending" check.
    real_open = invitation_service._open_invitation_by_token
    arrived = 0
    both_read = asyncio.Event()

    async def _synchronized_open(*args, **kwargs):
        nonlocal arrived
        invitation = await real_open(*args, **kwargs)
        arrived += 1
        if arrived == 2:
            both_read.set()
        try:
            await asyncio.wait_for(both_read.wait(), timeout=0.5)
        except TimeoutError:
            pass
        return invitation

    monkeypatch.setattr(invitation_service, "_open_invitation_by_token", _synchronized_open)

    async def _accept() -> str:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            try:
                await invitation_service.accept_invitation(
                    session, AcceptInvitationRequest(token=token, password=PASSWORD)
                )
            except AppError as exc:
                return exc.error_code
            return "ok"

    try:
        results = await asyncio.gather(_accept(), _accept())
        assert sorted(results) == ["invitation_used", "ok"]
        async with AsyncSession(engine) as check:
            users = (await check.scalars(select(User).where(User.email == email))).all()
            assert len(users) == 1
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(Invitation).where(Invitation.email == email))
            await cleanup.execute(delete(User).where(User.email == email))
            await cleanup.commit()


# ── Google ──────────────────────────────────────────────────────────────────


async def test_google_with_invitation_creates_staff_account(
    db_session: AsyncSession, monkeypatch
) -> None:
    email = _email()
    invitation, _ = await _add_invitation(db_session, email, role=UserRole.psychologist, locale="kk")
    _mock_google(monkeypatch, email)

    user, _ = await oauth_service.login_or_register_google("fake-token", db_session)

    assert user.role == UserRole.psychologist
    assert user.locale == "kk"
    assert user.is_verified is True
    await db_session.refresh(invitation)
    assert invitation.accepted_at is not None


async def test_google_adopts_unverified_account_with_invited_role(
    db_session: AsyncSession, monkeypatch
) -> None:
    email = _email()
    invitation, _ = await _add_invitation(db_session, email, role=UserRole.admin)
    squatter = await _add_user(db_session, email, is_verified=False)
    _mock_google(monkeypatch, email)

    user, _ = await oauth_service.login_or_register_google("fake-token", db_session)

    assert user.id == squatter.id
    assert user.role == UserRole.admin
    assert user.hashed_password is None
    await db_session.refresh(invitation)
    assert invitation.accepted_at is not None


async def test_google_keeps_verified_account_role_and_invitation_pending(
    db_session: AsyncSession, monkeypatch
) -> None:
    email = _email()
    invitation, _ = await _add_invitation(db_session, email, role=UserRole.admin)
    existing = await _add_user(db_session, email, is_verified=True)
    _mock_google(monkeypatch, email)

    user, _ = await oauth_service.login_or_register_google("fake-token", db_session)

    assert user.id == existing.id
    assert user.role == UserRole.student
    await db_session.refresh(invitation)
    assert invitation.accepted_at is None


@pytest.mark.parametrize(
    "invitation_state",
    [None, {"expires_in": timedelta(hours=-1)}, {"revoked": True}],
    ids=["no_invitation", "expired", "revoked"],
)
async def test_google_without_open_invitation_creates_student(
    db_session: AsyncSession, monkeypatch, invitation_state: dict | None
) -> None:
    email = _email()
    if invitation_state is not None:
        await _add_invitation(db_session, email, **invitation_state)
    _mock_google(monkeypatch, email)

    user, _ = await oauth_service.login_or_register_google("fake-token", db_session)

    assert user.role == UserRole.student


# ── rate limit ──────────────────────────────────────────────────────────────


async def test_accept_is_rate_limited(client: httpx.AsyncClient) -> None:
    statuses = [
        (await client.post(ACCEPT_URL, json={"token": uuid.uuid4().hex, "password": PASSWORD})).status_code
        for _ in range(11)
    ]

    assert statuses[:10] == [400] * 10
    assert statuses[10] == 429
