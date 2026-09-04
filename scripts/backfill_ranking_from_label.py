"""
Re-derives University.ranking from University.ranking_label using the fixed
parse_ranking() in seed_92_professions_universities.py (see
university-cards-ux-fix-plan.md §1 and docs/university-module-fix-plan.md
A5) — the seed script only sets `ranking` when a university row is first
created, so existing rows seeded before the parser fix keep their old
(sometimes wrong, mixing subject/national ranks into the "global" field)
value until this backfill runs.

NOT wired into cd.yml/cd-dev.yml — removed from both pipelines (along with
7 sibling one-time backfill_*.py scripts) once it had already corrected
every existing row in production; a completed backfill is a no-op forever
after (parse_ranking(ranking_label) stops disagreeing with ranking), so
running it on every future deploy serves no purpose. Kept here as a manual/
on-demand tool for whenever the parser itself changes again — the
is_locked(uni, "ranking") guard below (and
tests/unit/test_admin_university_lock.py::test_backfill_ranking_from_label_skips_locked_field)
protect an admin's PATCH-edited ranking on THAT run, not as a standing
production guarantee, since the script doesn't currently run on its own.

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
from app.services.admin_lock import is_locked
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
                if is_locked(uni, "ranking"):
                    print(f"Skipping ranking for {uni.name!r} ({uni.slug}) — admin-locked")
                    continue
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
