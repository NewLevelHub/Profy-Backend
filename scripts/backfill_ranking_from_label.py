"""
Re-derives University.ranking from University.ranking_label using the fixed
parse_ranking() in seed_92_professions_universities.py (see
university-cards-ux-fix-plan.md §1 and docs/university-module-fix-plan.md
A5) — the seed script only sets `ranking` when a university row is first
created, so existing rows seeded before the parser fix keep their old
(sometimes wrong, mixing subject/national ranks into the "global" field)
value until this backfill runs.

Dry-run by default — prints every row whose ranking would change, does not
write anything. Pass --apply to actually UPDATE the database.

Run inside the api container:
  docker exec profy-backend-api-1 python scripts/backfill_ranking_from_label.py [--apply]
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
    apply = "--apply" in sys.argv

    async with async_session() as db:
        universities = (
            (await db.execute(select(University).where(University.ranking_label.is_not(None))))
            .scalars()
            .all()
        )

        changed = 0
        for uni in universities:
            new_ranking = parse_ranking(uni.ranking_label)
            if new_ranking != uni.ranking:
                changed += 1
                print(
                    f"{'[would update]' if not apply else '[updating]'} "
                    f"{uni.name!r} ({uni.slug}): ranking {uni.ranking!r} -> {new_ranking!r} "
                    f"(label: {uni.ranking_label!r})"
                )
                if apply:
                    uni.ranking = new_ranking

        print(f"\n{changed} of {len(universities)} universities with a ranking_label would change.")

        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
