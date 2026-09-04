"""Applies scripts/data/foreign_university_dedup_review.json: for every
confirmed entry under "merges", moves the "remove" University row's photos,
programs, and external refs onto the "keep" row, then deletes the "remove"
row. Regenerate the file with scripts/generate_foreign_university_dedup_review.py
(it surfaces same-name / shared-ror_id / parenthetical-variant candidates
with program/photo/ror_id per side); a human sets `confirmed: true` and
fills `keep_slug` / `remove_slug`. Entries under "no_action" are genuine
sub-units or translation coincidences between different real institutions —
not touched by this script at all.

Merge mechanics copied from apply_kz_university_merge.py's _merge_one (same
partial-unique-index-on-is_primary caveat, same reason for a Core DELETE
instead of db.delete() to sidestep the ORM's relationship-cascade NULL
violation) — generalized here to move ALL external refs regardless of
`source`, not just "jinaq", since these merge pairs mix jinaq-imported and
older curated rows in both directions.

Resolves each side by `keep_slug` / `remove_slug` (falling back to
`keep_ror_id` / `remove_ror_id`) via scripts/entity_resolver.py — never by
a bare `University.id`, which is a per-database random uuid4() that does not
resolve on another DB (PRO-247; see
docs/content-pipeline-id-resolution-audit.md). Outcomes per pair:
  merged      both sides resolved to two distinct rows -> merge done
  already_done remove-side slug is gone, keep-side survives: a real prior run
  unresolved  neither side resolves, or only the keep side does, or the
              entry still uses the old bare-uuid schema -> the review file
              is stale for this pair, regenerate it (another run won't help)

Run inside the api container (writes nothing without --apply):
  docker-compose exec api python scripts/apply_foreign_university_dedup.py            # dry run
  docker-compose exec api python scripts/apply_foreign_university_dedup.py --apply
"""
import argparse
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from app.models.university_image import UniversityImage
from scripts.entity_resolver import resolve_university

REVIEW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "foreign_university_dedup_review.json")


async def _merge_rows(db, *, keep: University, remove: University) -> None:
    keep_id, remove_id = keep.id, remove.id

    target_has_primary = (
        await db.execute(
            select(UniversityImage).where(UniversityImage.university_id == keep_id, UniversityImage.is_primary.is_(True))
        )
    ).scalar_one_or_none() is not None

    images_result = await db.execute(select(UniversityImage).where(UniversityImage.university_id == remove_id))
    for image in images_result.scalars().all():
        was_primary = image.is_primary
        try:
            async with db.begin_nested():
                image.university_id = keep_id
                if was_primary and target_has_primary:
                    image.is_primary = False
                await db.flush()
        except IntegrityError:
            # keep-side already has an image with the same checksum (both
            # sides scraped/uploaded the identical photo) — redundant, drop it.
            await db.delete(image)
            await db.flush()
            continue
        if was_primary:
            target_has_primary = True

    programs_result = await db.execute(select(Program).where(Program.university_id == remove_id))
    for program in programs_result.scalars().all():
        try:
            async with db.begin_nested():
                program.university_id = keep_id
                await db.flush()
        except IntegrityError:
            # keep-side already has a program with the same normalized name.
            await db.delete(program)
            await db.flush()

    refs_result = await db.execute(select(UniversityExternalRef).where(UniversityExternalRef.university_id == remove_id))
    for ref in refs_result.scalars().all():
        ref.university_id = keep_id
        ref.match_method = "manual"

    await db.execute(delete(University).where(University.id == remove_id))


async def _resolve_side(db, entry: dict, side: str) -> University | None:
    return (
        await resolve_university(
            db, slug=entry.get(f"{side}_slug"), ror_id=entry.get(f"{side}_ror_id")
        )
    )[0]


async def main(*, apply: bool) -> None:
    with open(REVIEW_PATH, encoding="utf-8") as f:
        review = json.load(f)

    async with async_session() as db:
        merged = skipped_not_confirmed = already_done = unresolved = 0

        for entry in review["merges"]:
            if not entry.get("confirmed"):
                skipped_not_confirmed += 1
                continue

            label = entry.get("name") or entry.get("keep_slug") or "<pair>"

            if not entry.get("keep_slug") or not entry.get("remove_slug"):
                print(f"  UNRESOLVED: {label!r} has no keep_slug/remove_slug — regenerate the review file")
                unresolved += 1
                continue

            keep = await _resolve_side(db, entry, "keep")
            remove = await _resolve_side(db, entry, "remove")

            if keep is not None and remove is not None and keep.id != remove.id:
                print(f"merging {label!r}: {entry['remove_slug']} -> {entry['keep_slug']}")
                await _merge_rows(db, keep=keep, remove=remove)
                await db.flush()
                merged += 1
            elif keep is not None and (remove is None or remove.id == keep.id):
                already_done += 1
            else:
                print(
                    f"  UNRESOLVED: {label!r} — keep_slug={entry['keep_slug']!r} "
                    f"remove_slug={entry['remove_slug']!r} don't both resolve on this DB; regenerate the review file"
                )
                unresolved += 1

        if apply:
            await db.commit()
        else:
            await db.rollback()
            print("[dry-run] no changes committed")

        print(
            f"\nMerged: {merged}, already done (idempotent skip): {already_done}, "
            f"UNRESOLVED (stale review data): {unresolved}, not confirmed (left alone): {skipped_not_confirmed}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="commit changes (default: dry run)")
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)  # deprecated no-op alias
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
