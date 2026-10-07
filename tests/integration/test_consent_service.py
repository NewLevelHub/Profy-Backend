"""consent_service (PRO-291) — record_consent / has_consent round-trip.

Consent is recorded but never blocks anything in the MVP (PRO-282 §4); these
tests only assert the store/read behaviour the report sections rely on for
their `consent_ok` flag.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import CONSENT_SCOPE_PSYCH_BLOCK
from app.models.user import User
from app.services import consent_service


async def _make_user(db: AsyncSession) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    return user


async def test_record_consent_is_readable_back(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)

    consent = await consent_service.record_consent(
        db_session, user_id=user.id, signed_by="Родитель: Иванова А. А."
    )

    assert consent.id is not None
    assert consent.scope == CONSENT_SCOPE_PSYCH_BLOCK
    assert consent.assessment_id is None
    assert await consent_service.has_consent(db_session, user_id=user.id) is True


async def test_has_consent_is_false_when_nothing_signed(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    assert await consent_service.has_consent(db_session, user_id=user.id) is False


async def test_blanket_consent_covers_any_assessment(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    await consent_service.record_consent(
        db_session, user_id=user.id, signed_by="Законный представитель"
    )

    assert (
        await consent_service.has_consent(
            db_session, user_id=user.id, assessment_id=uuid.uuid4()
        )
        is True
    )


async def test_consent_is_scoped_to_its_user(db_session: AsyncSession) -> None:
    signer = await _make_user(db_session)
    other = await _make_user(db_session)
    await consent_service.record_consent(
        db_session, user_id=signer.id, signed_by="Родитель"
    )

    assert await consent_service.has_consent(db_session, user_id=other.id) is False


async def test_has_consent_respects_scope(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    await consent_service.record_consent(
        db_session, user_id=user.id, signed_by="Родитель"
    )

    assert (
        await consent_service.has_consent(
            db_session, user_id=user.id, scope="some_other_scope"
        )
        is False
    )
