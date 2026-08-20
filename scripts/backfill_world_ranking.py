"""One-off backfill: re-parses University.ranking_label for rows already
seeded before scripts/seed_92_professions_universities.py's parse_ranking()
learned to catch "1201+ (QS World)" / "Топ-100 (QS World)" style labels (not
just a leading "#N") — see WORLD_RANK_RE there for what it does and,
importantly, does NOT match (subject-specific "Top-N (X QS)" and national
"Top-N (Нац. рейтинг)" labels stay NULL on purpose, see that module's
comment). seed_92_professions_universities.py never updates existing rows on
rerun, so this is the one-time catch-up for rows created before the fix.

Idempotent: only touches rows where ranking IS NULL and a value is now
parseable; safe to re-run.

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/backfill_world_ranking.py [--dry-run]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.university import University
from scripts.seed_92_professions_universities import parse_ranking


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        result = await db.execute(
            select(University).where(University.ranking.is_(None), University.ranking_label.is_not(None))
        )
        candidates = result.scalars().all()

        updated = 0
        for u in candidates:
            new_rank = parse_ranking(u.ranking_label)
            if new_rank is not None:
                print(f"[rank] {u.slug}: NULL -> {new_rank}  ({u.ranking_label!r})")
                if not dry_run:
                    u.ranking = new_rank
                updated += 1

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}checked: {len(candidates)}, updated: {updated}")


if __name__ == "__main__":
    asyncio.run(main())
