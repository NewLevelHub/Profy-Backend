"""Applies scripts/data/foreign_university_dedup_review.json: for every
confirmed entry under "merges", moves the "remove" University row's photos,
programs, and external refs onto the "keep" row, then deletes the "remove"
row. See that file's _notes for how these 19 pairs were found (a
same-name-different-city signal and a shared-uniranks-profile signal, both
surfaced while running generate_uniranks_world_rank_review.py) and reviewed
(program/image counts, ovpo_code, ror_id per side). Entries under
"no_action" are genuine sub-units or translation coincidences between
different real institutions — not touched by this script at all.

Merge mechanics copied from apply_kz_university_merge.py's _merge_one (same
partial-unique-index-on-is_primary caveat, same reason for a Core DELETE
instead of db.delete() to sidestep the ORM's relationship-cascade NULL
violation) — generalized here to move ALL external refs regardless of
`source`, not just "jinaq", since these merge pairs mix jinaq-imported and
older curated rows in both directions.

Idempotent: matched by the review file's own "remove"/"keep" university_id
values — but unlike apply_kz_university_merge.py, these ids have no
portable equivalent to fall back on (no external_id in this review file,
only a combined display "name" string per pair, which isn't safe to
re-resolve automatically — see module docstring's caveat, same discipline
as apply_ovpo_codes.py's discarded fuzzy-matching attempt). So a
"remove" id that doesn't exist is logged as UNRESOLVED (not silently
"already done") unless the "keep" id it should have merged into still
exists — that combination is the only signal that actually distinguishes
"genuinely already merged here" from "these ids were never valid on this
database" (e.g. a snapshot taken from a different DB instance, since
University.id is a random uuid4() per row per database — see
apply_kz_university_merge.py's docstring for the general problem). An
UNRESOLVED pair needs the review file regenerated/re-matched against the
current database, not another run of this script.

Run inside the api container:
  docker-compose exec api python scripts/apply_foreign_university_dedup.py [--dry-run]
"""
import argparse
import asyncio
import json
import os
import sys
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from app.models.university_image import UniversityImage

REVIEW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "foreign_university_dedup_review.json")


async def _merge_one(db, *, remove_id: uuid.UUID, keep_id: uuid.UUID) -> str:
    """Returns "merged", "already_done", or "unresolved" — see module
    docstring for why these three outcomes aren't collapsible into a plain
    bool the way apply_kz_university_merge.py's are."""
    remove_uni = await db.get(University, remove_id)
    if remove_uni is None:
        keep_uni = await db.get(University, keep_id)
        if keep_uni is None:
            # Neither id exists on this DB — not a completed merge, the
            # review file's ids just don't match this database instance.
            return "unresolved"
        return "already_done"  # remove-side gone, keep-side survives: a real prior merge

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
    return "merged"


async def main(*, dry_run: bool) -> None:
    with open(REVIEW_PATH, encoding="utf-8") as f:
        review = json.load(f)

    async with async_session() as db:
        merged = skipped_not_confirmed = already_done = unresolved = 0

        for entry in review["merges"]:
            if not entry.get("confirmed"):
                skipped_not_confirmed += 1
                continue

            print(f"merging {entry['name']!r}: {entry['remove']} -> {entry['keep']}")
            outcome = await _merge_one(db, remove_id=uuid.UUID(entry["remove"]), keep_id=uuid.UUID(entry["keep"]))
            await db.flush()
            if outcome == "merged":
                merged += 1
            elif outcome == "already_done":
                already_done += 1
            else:
                print(
                    f"  UNRESOLVED: neither {entry['remove']} nor {entry['keep']} exists on this database — "
                    f"review data is stale for {entry['name']!r}, needs re-matching against the current DB"
                )
                unresolved += 1

        if dry_run:
            await db.rollback()
            print("[dry-run] no changes committed")
        else:
            await db.commit()

        print(
            f"\nMerged: {merged}, already done (idempotent skip): {already_done}, "
            f"UNRESOLVED (stale review data): {unresolved}, not confirmed (left alone): {skipped_not_confirmed}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
