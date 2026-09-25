"""PRO-427: one-time freeze of АСТУР attempts completed before result
snapshots existed.

Migration a7c3e1f9b2d4 marks fully submitted pre-PRO-427 attempts as
`completed` but cannot score them (scoring is app code). This script scores
each such attempt once, under the `legacy-1` formula against bank version 1,
and stores the frozen snapshot. Idempotent: attempts that already have a
snapshot are skipped, so running it on every deploy is a no-op once done.
Partial attempts are never touched (they stay in_progress / invalidated and
get no interpretation).

Run inside Docker: docker compose exec api python scripts/backfill_astur_legacy_snapshots.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.astur_run import AsturRun, AsturRunStatus
from app.services.astur.runs import freeze_legacy_snapshot


async def main() -> None:
    async with async_session() as db:
        runs = (
            await db.execute(
                select(AsturRun).where(
                    AsturRun.status == AsturRunStatus.completed, AsturRun.result_snapshot.is_(None)
                )
            )
        ).scalars().all()
        for run in runs:
            await freeze_legacy_snapshot(db, run)
        await db.commit()
        print(f"Frozen legacy АСТУР snapshots: {len(runs)}")


if __name__ == "__main__":
    asyncio.run(main())
