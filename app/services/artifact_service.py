import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact
from app.schemas.artifact import ArtifactItem


async def save_artifacts(
    profile_id: uuid.UUID,
    items: list[ArtifactItem],
    db: AsyncSession,
    *,
    commit: bool = True,
) -> list[Artifact]:
    """Replace all artifacts for `profile_id` with `items` (delete-then-insert).

    `commit=False` lets a caller fold this into a larger transaction (e.g.
    the combined profile+artifacts create endpoint, which commits once after
    both the Profile row and these artifacts are written) instead of ending
    the transaction here. The standalone `/profile/artifacts` endpoint keeps
    the default `commit=True`, unchanged from before.
    """
    async with db.begin_nested():
        await db.execute(delete(Artifact).where(Artifact.profile_id == profile_id))
        artifacts = [
            Artifact(profile_id=profile_id, type=item.type, value=item.value)
            for item in items
        ]
        db.add_all(artifacts)
    if commit:
        await db.commit()
    return artifacts


async def get_artifacts(profile_id: uuid.UUID, db: AsyncSession) -> list[Artifact]:
    result = await db.execute(select(Artifact).where(Artifact.profile_id == profile_id))
    return list(result.scalars().all())
