"""Assign/list extended blocks (Belbin/АСТУР) for an assessment (PRO-338,
post-Ф4.1 follow-up). See app/models/extended_block_assignment.py's own
docstring for why this is one-row-per-(assessment,block), not append-only,
and why completion is derived rather than stored."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extended_block_assignment import ExtendedBlock, ExtendedBlockAssignment
from app.services import astur_service, belbin_service


async def assign_block(
    assessment_id: uuid.UUID, block: ExtendedBlock, *, psychologist_id: uuid.UUID, db: AsyncSession
) -> ExtendedBlockAssignment:
    """Idempotent: assigning a block that's already assigned returns the
    existing row unchanged (not a second row, not an error) — a
    psychologist re-clicking "Назначить" is a no-op, not a mistake to
    reject."""
    existing = (
        await db.execute(
            select(ExtendedBlockAssignment).where(
                ExtendedBlockAssignment.assessment_id == assessment_id,
                ExtendedBlockAssignment.block == block,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    row = ExtendedBlockAssignment(
        assessment_id=assessment_id, block=block, psychologist_id=psychologist_id
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_assignments(assessment_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Every assigned block for this assessment, each with a `completed`
    flag derived from the corresponding append-only run table (never a
    stored flag — see the model's own docstring)."""
    rows = (
        await db.execute(
            select(ExtendedBlockAssignment)
            .where(ExtendedBlockAssignment.assessment_id == assessment_id)
            .order_by(ExtendedBlockAssignment.assigned_at)
        )
    ).scalars().all()

    result: list[dict] = []
    for row in rows:
        if row.block == ExtendedBlock.belbin:
            # Belbin's submit is one-shot (Ф2.4: all 7 blocks validated in a
            # single request) — a row existing at all means it's complete.
            run = await belbin_service.get_latest_run(assessment_id, db)
            completed = run is not None
        else:
            # АСТУР submits per-subtest (Ф3.4) — a row can exist mid-attempt,
            # so completion needs the same check submit_subtest itself uses.
            run = await astur_service.get_latest_run(assessment_id, db)
            completed = run is not None and astur_service.is_complete(run)
        result.append({
            "block": row.block.value,
            "assigned_at": row.assigned_at,
            "completed": completed,
        })
    return result
