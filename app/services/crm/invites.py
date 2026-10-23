"""Linking a deal to the student's Profile account (ТЗ §4.4, П2-10–П2-12).

The manager makes a one-time link in the deal; the student opens it, signs
up or signs in, and the account is tied to the deal. A new link revokes the
previous one. The owner can also link an existing account by its email.

Once linked, the specialist of the booked call gets the student, and the
deal follows the student's test and report (app/services/crm/progress.py).
"""

import base64
import hashlib
import secrets
import uuid
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.crm import CrmDeal, CrmDealEvent, CrmStudentInvite, DealResult
from app.models.user import User, UserRole
from app.schemas import crm as schemas
from app.services import audit, email_service, tz
from app.services.crm import progress
from app.services.crm.deals import SUPERVISORS, _require_open, _require_owned, crm_error, get_deal


def _hash(token: str) -> str:
    # 256 random bits: an unkeyed digest cannot be reversed by guessing.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _cipher() -> Fernet:
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"profile:crm-student-invite"
    ).derive(settings.SECRET_KEY.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def _url(token: str) -> str:
    # In the fragment: a browser never sends it, so the token stays out of logs.
    return email_service.frontend_url(f"/student-invite#token={token}")


def _invite_url(invite: CrmStudentInvite) -> str | None:
    try:
        return _url(_cipher().decrypt(invite.token_ciphertext.encode("ascii")).decode("ascii"))
    except InvalidToken:
        # SECRET_KEY changed since: a new link has to be made.
        return None


async def _open_invite(db: AsyncSession, deal_id: uuid.UUID) -> CrmStudentInvite | None:
    return await db.scalar(
        select(CrmStudentInvite)
        .where(
            CrmStudentInvite.deal_id == deal_id,
            CrmStudentInvite.used_at.is_(None),
            CrmStudentInvite.revoked_at.is_(None),
        )
        .order_by(CrmStudentInvite.created_at.desc())
        .limit(1)
    )


async def account_info(db: AsyncSession, deal: CrmDeal) -> schemas.StudentAccountOut:
    """The deal card's «Аккаунт ученика» block."""
    account = await db.get(User, deal.student_user_id) if deal.student_user_id else None
    invite = await _open_invite(db, deal.id)
    return schemas.StudentAccountOut(
        email=account.email if account else None,
        linked=account is not None,
        invite_url=_invite_url(invite) if invite else None,
        invite_created_at=invite.created_at if invite else None,
    )


def _event(db: AsyncSession, deal: CrmDeal, actor: User | None, kind: str, data: dict) -> None:
    db.add(CrmDealEvent(deal_id=deal.id, actor_id=actor.id if actor else None, kind=kind, data=data))


async def create_invite(db: AsyncSession, user: User, deal_id: uuid.UUID) -> CrmDeal:
    """A new link for the deal; the previous open one stops working."""
    deal = await get_deal(db, user, deal_id, for_update=True)
    _require_owned(user, deal)
    _require_open(deal)
    if deal.paid_at is None:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_not_paid")
    # With a specialist's call the link carries the specialist: it is made
    # once the call is booked and the system has picked who.
    if deal.psychologist_review and deal.specialist_id is None:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_not_booked")
    now = tz.now_utc()
    await db.execute(
        update(CrmStudentInvite)
        .where(
            CrmStudentInvite.deal_id == deal.id,
            CrmStudentInvite.used_at.is_(None),
            CrmStudentInvite.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    token = secrets.token_urlsafe(32)
    invite = CrmStudentInvite(
        deal_id=deal.id,
        token_hash=_hash(token),
        token_ciphertext=_cipher().encrypt(token.encode("ascii")).decode("ascii"),
        created_by=user.id,
    )
    db.add(invite)
    await db.flush()
    audit.record(
        db, actor=user, action="crm.student_invite_created", entity_type="crm_deal", entity_id=deal.id,
        after={"invite_id": str(invite.id)},
    )
    _event(db, deal, user, "invite", {"invite_id": str(invite.id)})
    await db.commit()
    return deal


async def _link(db: AsyncSession, deal: CrmDeal, student: User, actor: User | None, via: str) -> None:
    before = str(deal.student_user_id) if deal.student_user_id else None
    deal.student_user_id = student.id
    audit.record(
        db, actor=actor or student, action="crm.student_linked", entity_type="crm_deal", entity_id=deal.id,
        before={"student_user_id": before}, after={"student_user_id": str(student.id), "via": via},
    )
    _event(db, deal, actor, "student_linked", {"email": student.email, "via": via})
    await progress.assign_specialist(db, deal)
    await progress.sync_deal(db, deal)


async def require_open_invite(db: AsyncSession, token: str | None) -> None:
    """Signing up needs a live CRM link while registration is invite-only."""
    if not settings.REGISTRATION_INVITE_ONLY:
        return
    invite = await db.scalar(select(CrmStudentInvite).where(CrmStudentInvite.token_hash == _hash(token))) if token else None
    deal = await db.get(CrmDeal, invite.deal_id) if invite else None
    if invite is None or invite.used_at or invite.revoked_at or deal.result == DealResult.lost:
        raise crm_error(status.HTTP_403_FORBIDDEN, "registration_invite_only")


async def accept_invite(db: AsyncSession, student: User, token: str) -> None:
    """The signed-in student opens the link: the account joins the deal."""
    if student.role != UserRole.student:
        raise crm_error(status.HTTP_409_CONFLICT, "student_invite_students_only")
    invite = await db.scalar(
        select(CrmStudentInvite).where(CrmStudentInvite.token_hash == _hash(token)).with_for_update()
    )
    if invite is None or invite.revoked_at is not None:
        raise crm_error(status.HTTP_404_NOT_FOUND, "student_invite_invalid")
    if invite.used_at is not None:
        if invite.used_by == student.id:
            return  # Opened twice by the same student.
        raise crm_error(status.HTTP_404_NOT_FOUND, "student_invite_invalid")
    deal = await db.scalar(select(CrmDeal).where(CrmDeal.id == invite.deal_id).with_for_update())
    if deal.result == DealResult.lost:
        raise crm_error(status.HTTP_404_NOT_FOUND, "student_invite_invalid")
    invite.used_at = tz.now_utc()
    invite.used_by = student.id
    await _link(db, deal, student, None, "invite")
    await db.commit()


async def link_by_email(db: AsyncSession, user: User, deal_id: uuid.UUID, email: str) -> CrmDeal:
    """The owner's fallback (П2-12): tie an existing student account by email."""
    if user.role not in SUPERVISORS:
        raise crm_error(status.HTTP_403_FORBIDDEN, "student_link_forbidden")
    deal = await get_deal(db, user, deal_id, for_update=True)
    _require_open(deal)
    student = await db.scalar(select(User).where(User.email == email.strip().lower()))
    if student is None or student.role != UserRole.student:
        raise crm_error(status.HTTP_404_NOT_FOUND, "student_account_not_found")
    await _link(db, deal, student, user, "owner")
    await db.commit()
    return deal
