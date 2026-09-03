"""Applies scripts/data/uniranks_world_rank_review.json — writes
University.uniranks_world_rank for every entry with confirmed: true (see
generate_uniranks_world_rank_review.py for how these were found and why
"low" confidence entries were bulk-confirmed after a manual sample check
found them all correct, save one excluded branch-campus mismatch).

Deliberately does NOT touch uniranks_kz_rank or the generic `ranking`/
`ranking_label` fields — this pass is world-rank only, per explicit
instruction not to repeat the per-country-table approach used for
Kazakhstan (see apply_uniranks_kz_2027.py).

Resolves each row by a cross-DB-portable key — `jinaq_external_id` (via
university_external_refs) -> `slug` -> `ror_id`, through
scripts/entity_resolver.py — NOT by `university_id` (a per-database random
uuid4() snapshot that resolves to nothing on any other DB; see
docs/content-pipeline-id-resolution-audit.md). Run
enrich_uniranks_world_rank_review_keys.py once to backfill those keys into
an older copy of the review file. Idempotent: only writes when the stored
rank actually differs.

Run inside the api container (writes nothing without --apply):
  docker-compose exec api python scripts/apply_uniranks_world_rank.py            # dry run
  docker-compose exec api python scripts/apply_uniranks_world_rank.py --apply
"""
import argparse
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from app.database import async_session
from app.services.admin_lock import is_locked
from scripts.entity_resolver import resolve_university

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uniranks_world_rank_review.json")


async def main(*, apply: bool) -> None:
    with open(DATA_PATH, encoding="utf-8") as f:
        entries = json.load(f)

    confirmed = [e for e in entries if e.get("confirmed")]
    print(f"{len(confirmed)} confirmed of {len(entries)} total entries")

    async with async_session() as db:
        updated = 0
        skipped_needs_review = 0
        skipped_no_key = 0
        skipped_unresolved = 0
        skipped_locked = 0

        for entry in confirmed:
            if entry.get("needs_review"):
                skipped_needs_review += 1
                continue

            keys = {
                "jinaq_external_id": entry.get("jinaq_external_id"),
                "slug": entry.get("slug"),
                "ror_id": entry.get("ror_id"),
            }
            if not any(keys.values()):
                print(f"[skip:no-key] {entry['our_name']!r} — no portable key; re-run enrich_uniranks_world_rank_review_keys.py")
                skipped_no_key += 1
                continue

            university, matched_by = await resolve_university(db, **keys)
            if university is None:
                tried = ", ".join(f"{k}={v}" for k, v in keys.items() if v)
                print(f"[skip:unresolved] {entry['our_name']!r} — not on this DB ({tried})")
                skipped_unresolved += 1
                continue

            if university.uniranks_world_rank == entry["world_rank"]:
                continue

            if is_locked(university, "uniranks_world_rank"):
                print(f"Skipping uniranks_world_rank for {entry['our_name']!r} — admin-locked")
                skipped_locked += 1
                continue

            updated += 1
            if apply:
                university.uniranks_world_rank = entry["world_rank"]
            else:
                print(f"[would update] {entry['our_name']!r} (by {matched_by}) -> world_rank={entry['world_rank']}")

        if apply:
            await db.commit()

        print(
            f"\n{'' if apply else 'DRY RUN — '}updated: {updated}, "
            f"skipped (needs review): {skipped_needs_review}, skipped (no portable key): {skipped_no_key}, "
            f"skipped (unresolved on this DB): {skipped_unresolved}, skipped (admin-locked): {skipped_locked}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="commit changes (default: dry run)")
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)  # deprecated no-op alias
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
