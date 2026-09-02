"""Applies the human-reviewed scripts/data/jinaq/kz_university_merge_review.json:
for every entry with `confirmed: true` and a non-null `proposed_curated_match`,
merges the jinaq-created duplicate University row into the existing curated
row (moves its photos and specialties over, repoints the external ref, then
deletes the now-empty duplicate row). Entries with `confirmed: true` and a
null match need no action (they're confirmed genuinely-new universities).
An entry with a `rename_to` key (not a merge — a name correction on the
jinaq row itself, e.g. an outdated institution name) is handled separately
regardless of `confirmed`.

Never acts on an entry that isn't `confirmed: true` (or doesn't have
`rename_to`) — an unreviewed or rejected entry is left exactly as jinaq
created it.

Idempotent: re-running is a no-op for anything already merged. Matched by
the review file's `jinaq_external_id` via `university_external_refs`
(source="jinaq"), NOT by the review file's own `jinaq_university_id` field
— that field is a snapshot of `University.id` (a random uuid4() assigned
independently per row per database) taken from whatever DB the review was
generated against, so it does not resolve to the right row (or any row) on
a different database instance — every other environment (a fresh local
DB, prod on its first run of this pipeline) would silently no-op on every
entry, miscounted as "already done" rather than "never found a match".
`external_id` is jinaq's own source-system id, written into
university_external_refs by import_jinaq_universities.py on every import
regardless of which database it runs against, so it's the actually durable
key. After a successful merge the ref is repointed at the curated target,
so a re-run correctly recognizes "already merged" (ref.university_id ==
target) instead of treating the stale review-file id as authoritative.

Run inside the api container:
  docker-compose exec api python scripts/apply_kz_university_merge.py [--dry-run]
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
from app.services.admin_lock import is_locked

REVIEW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jinaq", "kz_university_merge_review.json")


async def _resolve_jinaq_university(db, external_id: str) -> University | None:
    """Looks up the current University row for a jinaq source id via
    university_external_refs — the only key that's stable across database
    instances (see module docstring)."""
    ref_result = await db.execute(
        select(UniversityExternalRef).where(
            UniversityExternalRef.source == "jinaq", UniversityExternalRef.external_id == external_id
        )
    )
    ref = ref_result.scalar_one_or_none()
    if ref is None:
        return None
    return await db.get(University, ref.university_id)


async def _merge_one(db, *, target_university_id: uuid.UUID, external_id: str) -> bool:
    jinaq_uni = await _resolve_jinaq_university(db, external_id)
    if jinaq_uni is None:
        return False  # jinaq row was never imported on this DB, or the ref is gone
    if jinaq_uni.id == target_university_id:
        return False  # already merged on a previous run — ref now points at the target itself
    jinaq_university_id = jinaq_uni.id

    target_has_primary = (
        await db.execute(
            select(UniversityImage).where(UniversityImage.university_id == target_university_id, UniversityImage.is_primary.is_(True))
        )
    ).scalar_one_or_none() is not None

    images_result = await db.execute(select(UniversityImage).where(UniversityImage.university_id == jinaq_university_id))
    for image in images_result.scalars().all():
        image.university_id = target_university_id
        # Two jinaq entries can merge into the same curated target (e.g. a
        # university and a since-absorbed institute within it) — the
        # partial unique index allows only one is_primary=true row per
        # university, so whichever image gets here second must yield.
        if image.is_primary and target_has_primary:
            image.is_primary = False
        elif image.is_primary:
            target_has_primary = True

    programs_result = await db.execute(select(Program).where(Program.university_id == jinaq_university_id))
    for program in programs_result.scalars().all():
        try:
            async with db.begin_nested():
                program.university_id = target_university_id
                await db.flush()
        except IntegrityError:
            # target already has a program with the same normalized name —
            # redundant with what the curated row already offers, drop it.
            await db.delete(program)
            await db.flush()

    ref_result = await db.execute(
        select(UniversityExternalRef).where(
            UniversityExternalRef.source == "jinaq", UniversityExternalRef.external_id == external_id
        )
    )
    ref = ref_result.scalar_one_or_none()
    if ref is not None:
        ref.university_id = target_university_id
        ref.match_method = "manual"

    # Plain Core DELETE, not db.delete(jinaq_uni) — the ORM delete tries to
    # cascade-null University.programs for any Program still associated with
    # this id in the session's relationship state, even ones already
    # repointed above by direct attribute assignment (their in-memory
    # collection membership on the University side doesn't auto-update from
    # that), which collides with Program.university_id's NOT NULL
    # constraint. By now nothing real still references this row (everything
    # was moved or deleted above), so a bare DELETE is both correct and
    # side-effect-free.
    await db.execute(delete(University).where(University.id == jinaq_university_id))
    return True


async def main(*, dry_run: bool) -> None:
    with open(REVIEW_PATH, encoding="utf-8") as f:
        review = json.load(f)

    async with async_session() as db:
        merged = skipped_not_confirmed = skipped_no_match = already_done = renamed = 0

        for entry in review["entries"]:
            if entry.get("rename_to"):
                jinaq_uni = await _resolve_jinaq_university(db, entry["jinaq_external_id"])
                if jinaq_uni is None:
                    continue
                if is_locked(jinaq_uni, "name"):
                    print(f"Skipping name for {jinaq_uni.id} — admin-locked")
                else:
                    jinaq_uni.name = entry["rename_to"]
                    renamed += 1
                if entry.get("short_name_to"):
                    if is_locked(jinaq_uni, "short_name"):
                        print(f"Skipping short_name for {jinaq_uni.id} — admin-locked")
                    else:
                        jinaq_uni.short_name = entry["short_name_to"]
                continue

            if not entry["confirmed"]:
                skipped_not_confirmed += 1
                continue
            if not entry["proposed_curated_match"]:
                skipped_no_match += 1
                continue

            target_result = await db.execute(
                select(University).where(University.slug == entry["proposed_curated_match"]["slug"])
            )
            target = target_result.scalar_one_or_none()
            if target is None:
                print(f"WARNING: target slug {entry['proposed_curated_match']['slug']!r} not found, skipping {entry['jinaq_name']!r}")
                continue
            target_id = target.id
            print(f"merging {entry['jinaq_name']!r} (jinaq external_id={entry['jinaq_external_id']}) -> {entry['proposed_curated_match']['slug']!r} ({target_id})")

            did_merge = await _merge_one(
                db,
                target_university_id=target_id,
                external_id=entry["jinaq_external_id"],
            )
            await db.flush()
            if did_merge:
                merged += 1
            else:
                already_done += 1

        if dry_run:
            await db.rollback()
            print("[dry-run] no changes committed")
        else:
            await db.commit()

        print(
            f"Merged: {merged}, already done (idempotent skip): {already_done}, renamed: {renamed}, "
            f"not confirmed (left alone): {skipped_not_confirmed}, confirmed no-match (left alone): {skipped_no_match}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
