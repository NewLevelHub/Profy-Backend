"""Admin invitation endpoints (PRO-460) against
docs/frontend-admin-invitations-api-contract.md §3."""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation
from app.models.user import User, UserRole
from app.services import auth_service, email_service
from app.services.invitation_service import hash_token

URL = "/api/v1/admin/invitations"


@pytest.fixture
def sent_emails(monkeypatch) -> list[dict]:
    captured: list[dict] = []

    async def _capture(to: str, invite_url: str, *, role: UserRole, locale: str) -> None:
        captured.append({"to": to, "invite_url": invite_url, "role": role, "locale": locale})

    monkeypatch.setattr(email_service, "send_invitation_email", _capture)
    return captured


def _email() -> str:
    return f"{uuid.uuid4()}@example.com"


def _token(invite_url: str) -> str:
    return parse_qs(urlparse(invite_url).query)["token"][0]


async def _add_invitation(
    db: AsyncSession,
    email: str,
    *,
    expires_in: timedelta = timedelta(hours=72),
    accepted: bool = False,
    revoked: bool = False,
) -> Invitation:
    now = datetime.now(timezone.utc)
    invitation = Invitation(
        email=email,
        role=UserRole.psychologist,
        locale="ru",
        token_hash=hash_token(uuid.uuid4().hex),
        expires_at=now + expires_in,
        accepted_at=now if accepted else None,
        revoked_at=now if revoked else None,
    )
    db.add(invitation)
    await db.flush()
    return invitation


async def _add_user(db: AsyncSession, email: str, *, role: UserRole, is_verified: bool) -> None:
    db.add(
        User(
            email=email,
            hashed_password=auth_service.hash_password("Testpass123!"),
            role=role,
            is_verified=is_verified,
        )
    )
    await db.flush()


# ── create ──────────────────────────────────────────────────────────────────


async def test_create_stores_invitation_without_user_and_sends_email(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    admin_user: User,
    db_session: AsyncSession,
    sent_emails: list[dict],
) -> None:
    email = _email()
    response = await client.post(
        URL, json={"email": email.upper(), "role": "psychologist", "locale": "kk"}, headers=admin_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["role"] == "psychologist"
    assert body["locale"] == "kk"
    assert body["status"] == "pending"
    assert body["invited_by"] == {"id": str(admin_user.id), "email": admin_user.email}
    assert body["email_sent"] is True
    assert body["accepted_at"] is None and body["revoked_at"] is None

    invitation = await db_session.scalar(select(Invitation).where(Invitation.email == email))
    assert invitation is not None
    assert invitation.token_hash == hash_token(_token(body["invite_url"]))
    ttl = invitation.expires_at - invitation.created_at
    assert timedelta(hours=71) < ttl <= timedelta(hours=72, minutes=1)
    assert await db_session.scalar(select(User).where(User.email == email)) is None

    assert sent_emails == [
        {"to": email, "invite_url": body["invite_url"], "role": UserRole.psychologist, "locale": "kk"}
    ]
    assert body["invite_url"].startswith(email_service.frontend_url("/invite?token="))


async def test_create_defaults_locale_to_ru(
    client: httpx.AsyncClient, admin_headers: dict[str, str], sent_emails: list[dict]
) -> None:
    response = await client.post(URL, json={"email": _email(), "role": "admin"}, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["locale"] == "ru"
    assert response.json()["role"] == "admin"


@pytest.mark.parametrize(
    "payload",
    [
        {"role": "student"},
        {"role": "psychologist", "locale": "en"},
        {"role": "psychologist", "email": "not-an-email"},
    ],
    ids=["student_role", "unknown_locale", "bad_email"],
)
async def test_create_rejects_invalid_body(
    client: httpx.AsyncClient, admin_headers: dict[str, str], sent_emails: list[dict], payload: dict
) -> None:
    response = await client.post(URL, json={"email": _email(), **payload}, headers=admin_headers)

    assert response.status_code == 422
    assert sent_emails == []


@pytest.mark.parametrize("role", [UserRole.student, UserRole.psychologist])
async def test_create_conflicts_with_verified_user(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    sent_emails: list[dict],
    role: UserRole,
) -> None:
    email = _email()
    await _add_user(db_session, email, role=role, is_verified=True)

    response = await client.post(URL, json={"email": email, "role": "psychologist"}, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error_code"] == "user_exists"
    assert sent_emails == []


async def test_unverified_user_does_not_block_create(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    sent_emails: list[dict],
) -> None:
    email = _email()
    await _add_user(db_session, email, role=UserRole.student, is_verified=False)

    response = await client.post(URL, json={"email": email, "role": "psychologist"}, headers=admin_headers)

    assert response.status_code == 201


async def test_create_conflicts_with_pending_invitation(
    client: httpx.AsyncClient, admin_headers: dict[str, str], sent_emails: list[dict]
) -> None:
    email = _email()
    first = await client.post(URL, json={"email": email, "role": "psychologist"}, headers=admin_headers)
    second = await client.post(URL, json={"email": email, "role": "admin"}, headers=admin_headers)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error_code"] == "invitation_pending"
    assert len(sent_emails) == 1


@pytest.mark.parametrize(
    "closed",
    [{"expires_in": timedelta(hours=-1)}, {"revoked": True}, {"accepted": True}],
    ids=["expired", "revoked", "accepted"],
)
async def test_closed_invitations_do_not_block_create(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    sent_emails: list[dict],
    closed: dict,
) -> None:
    email = _email()
    await _add_invitation(db_session, email, **closed)

    response = await client.post(URL, json={"email": email, "role": "psychologist"}, headers=admin_headers)

    assert response.status_code == 201


async def test_create_survives_email_provider_failure(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, monkeypatch
) -> None:
    async def _fail(*_args, **_kwargs) -> None:
        raise RuntimeError("resend down")

    monkeypatch.setattr(email_service, "send_invitation_email", _fail)
    email = _email()

    response = await client.post(URL, json={"email": email, "role": "psychologist"}, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["email_sent"] is False
    assert response.json()["invite_url"]
    assert await db_session.scalar(select(Invitation).where(Invitation.email == email)) is not None


# ── resend ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("expires_in", [timedelta(hours=1), timedelta(hours=-1)], ids=["pending", "expired"])
async def test_resend_replaces_token_and_restarts_ttl(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    sent_emails: list[dict],
    expires_in: timedelta,
) -> None:
    invitation = await _add_invitation(db_session, _email(), expires_in=expires_in)
    old_hash = invitation.token_hash

    response = await client.post(f"{URL}/{invitation.id}/resend", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(invitation.id)
    assert body["status"] == "pending"
    assert body["email_sent"] is True
    await db_session.refresh(invitation)
    assert invitation.token_hash == hash_token(_token(body["invite_url"]))
    assert invitation.token_hash != old_hash
    assert await db_session.scalar(select(Invitation).where(Invitation.token_hash == old_hash)) is None
    assert invitation.expires_at > datetime.now(timezone.utc) + timedelta(hours=71)
    assert [m["invite_url"] for m in sent_emails] == [body["invite_url"]]


@pytest.mark.parametrize(
    ("closed", "error_code"),
    [({"accepted": True}, "invitation_used"), ({"revoked": True}, "invitation_revoked")],
    ids=["accepted", "revoked"],
)
async def test_resend_rejects_closed_invitation(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    sent_emails: list[dict],
    closed: dict,
    error_code: str,
) -> None:
    invitation = await _add_invitation(db_session, _email(), **closed)

    response = await client.post(f"{URL}/{invitation.id}/resend", headers=admin_headers)

    assert response.status_code == 400
    assert response.json()["error_code"] == error_code
    assert sent_emails == []


async def test_resend_of_expired_conflicts_with_newer_pending(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, sent_emails: list[dict]
) -> None:
    email = _email()
    expired = await _add_invitation(db_session, email, expires_in=timedelta(hours=-1))
    await _add_invitation(db_session, email)

    response = await client.post(f"{URL}/{expired.id}/resend", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error_code"] == "invitation_pending"


async def test_resend_conflicts_with_user_registered_meanwhile(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, sent_emails: list[dict]
) -> None:
    email = _email()
    invitation = await _add_invitation(db_session, email)
    await _add_user(db_session, email, role=UserRole.student, is_verified=True)

    response = await client.post(f"{URL}/{invitation.id}/resend", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error_code"] == "user_exists"


# ── revoke ──────────────────────────────────────────────────────────────────


async def test_revoke_pending_invitation(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    invitation = await _add_invitation(db_session, _email())

    response = await client.delete(f"{URL}/{invitation.id}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert response.json()["revoked_at"] is not None
    await db_session.refresh(invitation)
    assert invitation.revoked_at is not None


@pytest.mark.parametrize(
    ("closed", "error_code"),
    [
        ({"accepted": True}, "invitation_used"),
        ({"revoked": True}, "invitation_revoked"),
        ({"expires_in": timedelta(hours=-1)}, "invitation_expired"),
    ],
    ids=["accepted", "revoked", "expired"],
)
async def test_revoke_rejects_non_pending(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    closed: dict,
    error_code: str,
) -> None:
    invitation = await _add_invitation(db_session, _email(), **closed)

    response = await client.delete(f"{URL}/{invitation.id}", headers=admin_headers)

    assert response.status_code == 400
    assert response.json()["error_code"] == error_code


@pytest.mark.parametrize("method", ["resend", "revoke"])
async def test_unknown_invitation_is_404(
    client: httpx.AsyncClient, admin_headers: dict[str, str], method: str
) -> None:
    missing = uuid.uuid4()
    if method == "resend":
        response = await client.post(f"{URL}/{missing}/resend", headers=admin_headers)
    else:
        response = await client.delete(f"{URL}/{missing}", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "invitation_not_found"


# ── list ────────────────────────────────────────────────────────────────────


async def test_list_reports_derived_statuses_and_filters(
    client: httpx.AsyncClient, admin_headers: dict[str, str], admin_user: User, db_session: AsyncSession
) -> None:
    domain = f"{uuid.uuid4().hex}.example.com"
    pending = await _add_invitation(db_session, f"pending@{domain}")
    pending.invited_by = admin_user.id
    await _add_invitation(db_session, f"expired@{domain}", expires_in=timedelta(hours=-1))
    await _add_invitation(db_session, f"revoked@{domain}", revoked=True)
    # Accepted after its deadline passed — still "accepted", not "expired".
    await _add_invitation(db_session, f"accepted@{domain}", accepted=True, expires_in=timedelta(hours=-1))
    await db_session.flush()

    response = await client.get(URL, params={"search": domain}, headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    statuses = {item["email"].split("@")[0]: item["status"] for item in body["items"]}
    assert statuses == {
        "pending": "pending",
        "expired": "expired",
        "revoked": "revoked",
        "accepted": "accepted",
    }
    by_email = {item["email"]: item for item in body["items"]}
    assert by_email[f"pending@{domain}"]["invited_by"] == {"id": str(admin_user.id), "email": admin_user.email}
    assert by_email[f"expired@{domain}"]["invited_by"] is None
    assert "invite_url" not in body["items"][0]

    for status in ("pending", "expired", "revoked", "accepted"):
        filtered = await client.get(URL, params={"search": domain, "status": status}, headers=admin_headers)
        assert [item["email"] for item in filtered.json()["items"]] == [f"{status}@{domain}"]


async def test_list_paginates_newest_first(
    client: httpx.AsyncClient, admin_headers: dict[str, str], sent_emails: list[dict]
) -> None:
    domain = f"{uuid.uuid4().hex}.example.com"
    for name in ("a", "b", "c"):
        response = await client.post(URL, json={"email": f"{name}@{domain}", "role": "psychologist"}, headers=admin_headers)
        assert response.status_code == 201

    page1 = await client.get(URL, params={"search": domain, "limit": 2, "page": 1}, headers=admin_headers)
    page2 = await client.get(URL, params={"search": domain, "limit": 2, "page": 2}, headers=admin_headers)

    assert page1.json()["total"] == 3
    emails = [i["email"] for i in page1.json()["items"] + page2.json()["items"]]
    assert sorted(emails) == [f"{n}@{domain}" for n in ("a", "b", "c")]
    assert len(page1.json()["items"]) == 2 and len(page2.json()["items"]) == 1


# ── access ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", [UserRole.student, UserRole.psychologist])
async def test_non_admin_gets_403_everywhere(
    client: httpx.AsyncClient, db_session: AsyncSession, role: UserRole
) -> None:
    email = _email()
    await _add_user(db_session, email, role=role, is_verified=True)
    user = await db_session.scalar(select(User).where(User.email == email))
    headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(user)}"}
    some_id = uuid.uuid4()
    responses = [
        await client.post(URL, json={"email": _email(), "role": "psychologist"}, headers=headers),
        await client.get(URL, headers=headers),
        await client.post(f"{URL}/{some_id}/resend", headers=headers),
        await client.delete(f"{URL}/{some_id}", headers=headers),
    ]

    assert [r.status_code for r in responses] == [403, 403, 403, 403]
