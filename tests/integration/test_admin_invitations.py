"""Admin invitation endpoints (PRO-460) against
docs/frontend-admin-invitations-api-contract.md §3."""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from email_validator import EmailUndeliverableError

from app.models.invitation import Invitation, InvitationEmailStatus
from app.models.user import User, UserRole
from app.services import auth_service, email_service, invitation_service
from app.services.invitation_service import hash_token

URL = "/api/v1/admin/invitations"


@pytest.fixture
def sent_emails(monkeypatch) -> list[dict]:
    captured: list[dict] = []

    async def _capture(to: str, invite_url: str, *, role: UserRole, locale: str) -> str:
        captured.append({"to": to, "invite_url": invite_url, "role": role, "locale": locale})
        return f"msg-{uuid.uuid4()}"

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
    assert body["email_status"] == "sent"
    assert body["accepted_at"] is None and body["revoked_at"] is None

    invitation = await db_session.scalar(select(Invitation).where(Invitation.email == email))
    assert invitation is not None
    assert invitation.token_hash == hash_token(_token(body["invite_url"]))
    assert invitation.email_message_id is not None
    assert invitation.email_status == InvitationEmailStatus.sent
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
    assert response.json()["email_status"] == "failed"
    assert response.json()["invite_url"]
    assert await db_session.scalar(select(Invitation).where(Invitation.email == email)) is not None


async def test_create_without_email_configured_reports_not_sent(
    client: httpx.AsyncClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    """Real email_service, no RESEND_API_KEY: the admin must see that nothing went out."""
    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "")

    response = await client.post(URL, json={"email": _email(), "role": "psychologist"}, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["email_sent"] is False


async def test_create_rejects_domain_without_mail(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    sent_emails: list[dict],
    monkeypatch,
) -> None:
    """A made-up domain must not turn into "email sent"."""
    checked: list[str] = []

    def _no_mx(email: str, **_kwargs) -> None:
        checked.append(email)
        raise EmailUndeliverableError("The domain name does not exist.")

    monkeypatch.setattr(invitation_service.settings, "INVITATION_CHECK_DELIVERABILITY", True)
    monkeypatch.setattr(invitation_service, "validate_email", _no_mx)
    email = _email()

    response = await client.post(URL, json={"email": email, "role": "psychologist"}, headers=admin_headers)

    assert response.status_code == 422
    assert response.json()["error_code"] == "invitation_email_undeliverable"
    assert checked == [email]
    assert sent_emails == []
    assert await db_session.scalar(select(Invitation).where(Invitation.email == email)) is None


async def test_create_checks_mail_domain_when_enabled(
    client: httpx.AsyncClient, admin_headers: dict[str, str], sent_emails: list[dict], monkeypatch
) -> None:
    calls: list[dict] = []

    def _deliverable(email: str, **kwargs) -> None:
        calls.append({"email": email, **kwargs})

    monkeypatch.setattr(invitation_service.settings, "INVITATION_CHECK_DELIVERABILITY", True)
    monkeypatch.setattr(invitation_service, "validate_email", _deliverable)

    response = await client.post(URL, json={"email": _email(), "role": "psychologist"}, headers=admin_headers)

    assert response.status_code == 201
    assert calls[0]["check_deliverability"] is True


# An authenticated request takes the locale from `users.locale` first.
@pytest.mark.parametrize(
    ("payload", "admin_locale", "message"),
    [
        ({"role": "student"}, "ru", "Пригласить можно только психолога или админа"),
        ({"role": "superuser"}, "kk", "Тек психологты немесе әкімшіні шақыруға болады"),
        ({"role": "psychologist", "email": "not-an-email"}, "ru", "Введите корректный email"),
        ({"role": "psychologist", "locale": "en"}, "ru", "Язык письма должен быть одним из: ru, kk"),
    ],
    ids=["student_ru", "unknown_role_kk", "bad_email_ru", "bad_locale"],
)
async def test_validation_errors_are_localized(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    admin_user: User,
    payload: dict,
    admin_locale: str,
    message: str,
) -> None:
    admin_user.locale = admin_locale

    response = await client.post(URL, json={"email": _email(), **payload}, headers=admin_headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == message


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
    assert body["email_status"] == "sent"
    await db_session.refresh(invitation)
    assert invitation.token_hash == hash_token(_token(body["invite_url"]))
    assert invitation.token_hash != old_hash
    assert await db_session.scalar(select(Invitation).where(Invitation.token_hash == old_hash)) is None
    assert invitation.expires_at > datetime.now(timezone.utc) + timedelta(hours=71)
    assert [m["invite_url"] for m in sent_emails] == [body["invite_url"]]


async def test_resend_overtaken_by_another_resend_is_409_and_keeps_the_newer_email(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, monkeypatch
) -> None:
    """Another admin's resend replaces the token while this email is going
    out: this request must not hand back its now-dead link, nor overwrite
    the newer email's id (webhook events are matched by it)."""
    invitation = await _add_invitation(db_session, _email())

    async def _overtaken(*_args, **_kwargs) -> str:
        await db_session.execute(
            update(Invitation)
            .where(Invitation.id == invitation.id)
            .values(
                token_hash=hash_token("newer-token"),
                email_message_id="msg-newer",
                email_status=InvitationEmailStatus.sent,
            )
        )
        return "msg-older"

    monkeypatch.setattr(email_service, "send_invitation_email", _overtaken)

    response = await client.post(f"{URL}/{invitation.id}/resend", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error_code"] == "invitation_superseded"
    await db_session.refresh(invitation)
    assert invitation.token_hash == hash_token("newer-token")
    assert invitation.email_message_id == "msg-newer"


@pytest.mark.parametrize("closed_field", ["revoked_at", "accepted_at"])
async def test_resend_overtaken_by_closure_is_409_and_does_not_record_the_email(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    monkeypatch,
    closed_field: str,
) -> None:
    """A revoke or accept while the provider call is in flight closes the
    token even though its hash stays on the row. The response must not expose
    that dead link or attach the provider message to the closed invitation."""
    invitation = await _add_invitation(db_session, _email())

    async def _closed_while_sending(*_args, **_kwargs) -> str:
        await db_session.execute(
            update(Invitation)
            .where(Invitation.id == invitation.id)
            .values(**{closed_field: datetime.now(timezone.utc), "token_ciphertext": None})
        )
        return "msg-after-close"

    monkeypatch.setattr(email_service, "send_invitation_email", _closed_while_sending)

    response = await client.post(f"{URL}/{invitation.id}/resend", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error_code"] == "invitation_superseded"
    await db_session.refresh(invitation)
    assert getattr(invitation, closed_field) is not None
    assert invitation.email_message_id is None
    assert invitation.email_status is None


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
    assert invitation.token_ciphertext is None


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


@pytest.mark.parametrize("method", ["resend", "revoke", "link"])
async def test_unknown_invitation_is_404(
    client: httpx.AsyncClient, admin_headers: dict[str, str], method: str
) -> None:
    missing = uuid.uuid4()
    if method == "resend":
        response = await client.post(f"{URL}/{missing}/resend", headers=admin_headers)
    elif method == "link":
        response = await client.get(f"{URL}/{missing}/link", headers=admin_headers)
    else:
        response = await client.delete(f"{URL}/{missing}", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["error_code"] == "invitation_not_found"


# ── link ────────────────────────────────────────────────────────────────────


async def test_link_of_pending_invitation_is_the_emailed_one(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, sent_emails: list[dict]
) -> None:
    created = await client.post(URL, json={"email": _email(), "role": "psychologist"}, headers=admin_headers)
    invitation_id = created.json()["id"]

    link = await client.get(f"{URL}/{invitation_id}/link", headers=admin_headers)

    assert link.status_code == 200
    assert link.json()["invite_url"] == created.json()["invite_url"] == sent_emails[0]["invite_url"]
    assert link.json()["expires_at"] == created.json()["expires_at"]
    # Stored encrypted, not as the raw token.
    invitation = await db_session.get(Invitation, uuid.UUID(invitation_id))
    assert invitation.token_ciphertext
    assert _token(created.json()["invite_url"]) not in invitation.token_ciphertext


async def test_link_follows_resend(
    client: httpx.AsyncClient, admin_headers: dict[str, str], sent_emails: list[dict]
) -> None:
    created = await client.post(URL, json={"email": _email(), "role": "psychologist"}, headers=admin_headers)
    invitation_id = created.json()["id"]
    resent = await client.post(f"{URL}/{invitation_id}/resend", headers=admin_headers)

    link = await client.get(f"{URL}/{invitation_id}/link", headers=admin_headers)

    assert link.json()["invite_url"] == resent.json()["invite_url"]
    assert link.json()["invite_url"] != created.json()["invite_url"]


@pytest.mark.parametrize(
    ("closed", "error_code"),
    [
        ({"accepted": True}, "invitation_used"),
        ({"revoked": True}, "invitation_revoked"),
        ({"expires_in": timedelta(hours=-1)}, "invitation_expired"),
    ],
    ids=["accepted", "revoked", "expired"],
)
async def test_link_of_closed_invitation_is_400(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    closed: dict,
    error_code: str,
) -> None:
    invitation = await _add_invitation(db_session, _email(), **closed)

    response = await client.get(f"{URL}/{invitation.id}/link", headers=admin_headers)

    assert response.status_code == 400
    assert response.json()["error_code"] == error_code


async def test_link_without_stored_token_is_409(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Rows from before links were kept (or after a SECRET_KEY change)."""
    invitation = await _add_invitation(db_session, _email())
    assert invitation.token_ciphertext is None

    response = await client.get(f"{URL}/{invitation.id}/link", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error_code"] == "invitation_link_unavailable"


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
    assert by_email[f"pending@{domain}"]["email_status"] is None

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
        await client.get(f"{URL}/{some_id}/link", headers=headers),
    ]

    assert [r.status_code for r in responses] == [403, 403, 403, 403, 403]
