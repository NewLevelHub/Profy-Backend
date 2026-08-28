import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.certificate import Certificate
from app.schemas.certificate import CertificateItem


async def save_certificates(
    profile_id: uuid.UUID,
    items: list[CertificateItem],
    db: AsyncSession,
    *,
    commit: bool = True,
) -> list[Certificate]:
    """Replace all certificates for `profile_id` with `items` (delete-then-insert).

    `commit=False` lets a caller fold this into a larger transaction (e.g.
    the combined profile+certificates create/update endpoints), mirroring
    app/services/artifact_service.py::save_artifacts.
    """
    async with db.begin_nested():
        await db.execute(delete(Certificate).where(Certificate.profile_id == profile_id))
        certificates = [
            Certificate(profile_id=profile_id, type=item.type, score=item.score)
            for item in items
        ]
        db.add_all(certificates)
    if commit:
        await db.commit()
    return certificates


async def get_certificates(profile_id: uuid.UUID, db: AsyncSession) -> list[Certificate]:
    result = await db.execute(select(Certificate).where(Certificate.profile_id == profile_id))
    return list(result.scalars().all())
