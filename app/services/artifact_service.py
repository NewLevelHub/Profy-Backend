import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact
from app.schemas.artifact import ArtifactItem


async def save_artifacts(profile_id: uuid.UUID, items: list[ArtifactItem], db: AsyncSession) -> list[Artifact]:
    await db.execute(delete(Artifact).where(Artifact.profile_id == profile_id))

    artifacts = [
        Artifact(profile_id=profile_id, type=item.type, value=item.value)
        for item in items
    ]
    db.add_all(artifacts)
    await db.commit()
    return artifacts


async def get_artifacts(profile_id: uuid.UUID, db: AsyncSession) -> list[Artifact]:
    result = await db.execute(select(Artifact).where(Artifact.profile_id == profile_id))
    return list(result.scalars().all())
