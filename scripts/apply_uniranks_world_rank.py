"""Applies scripts/data/uniranks_world_rank_review.json — writes
University.uniranks_world_rank for every entry with confirmed: true (see
generate_uniranks_world_rank_review.py for how these were found and why
"low" confidence entries were bulk-confirmed after a manual sample check
found them all correct, save one excluded branch-campus mismatch).

Deliberately does NOT touch uniranks_kz_rank or the generic `ranking`/
`ranking_label` fields — this pass is world-rank only, per explicit
instruction not to repeat the per-country-table approach used for
Kazakhstan (see apply_uniranks_kz_2027.py).

Idempotent: matches by University.id (not name), so re-running with the
same file is a no-op after the first successful apply.

Run inside the api container:
  docker-compose exec api python scripts/apply_uniranks_world_rank.py [--dry-run]
"""
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.university import University
from app.services.admin_lock import is_locked

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uniranks_world_rank_review.json")


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    with open(DATA_PATH, encoding="utf-8") as f:
        entries = json.load(f)

    confirmed = [e for e in entries if e.get("confirmed")]
    print(f"{len(confirmed)} confirmed of {len(entries)} total entries")

    async with async_session() as db:
        updated = 0
        skipped_missing = 0
        skipped_locked = 0

        for entry in confirmed:
            result = await db.execute(select(University).where(University.id == entry["university_id"]))
            university = result.scalar_one_or_none()
            if university is None:
                print(f"[skip] {entry['our_name']!r} -> id {entry['university_id']} not found in DB")
                skipped_missing += 1
                continue

            if university.uniranks_world_rank == entry["world_rank"]:
                continue

            if is_locked(university, "uniranks_world_rank"):
                print(f"Skipping uniranks_world_rank for {entry['our_name']!r} — admin-locked")
                skipped_locked += 1
                continue

            updated += 1
            if dry_run:
                print(f"[would update] {entry['our_name']!r} -> world_rank={entry['world_rank']}")
            else:
                university.uniranks_world_rank = entry["world_rank"]

        if not dry_run:
            await db.commit()

        print(
            f"\n{'DRY RUN — ' if dry_run else ''}updated: {updated}, "
            f"skipped (not found): {skipped_missing}, skipped (admin-locked): {skipped_locked}"
        )


if __name__ == "__main__":
    asyncio.run(main())
