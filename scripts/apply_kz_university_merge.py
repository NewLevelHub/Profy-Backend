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

Resolves the jinaq row by the review file's `jinaq_external_id` through
university_external_refs (source="jinaq"), NOT by its `jinaq_university_id`
field — that is a snapshot of `University.id` (a per-database random
uuid4()) and resolves to nothing on any other database instance, so every
fresh environment (a new local DB, prod's first pipeline run) would
silently no-op on every entry. `external_id` is jinaq's own source id,
written into university_external_refs by import_jinaq_universities.py on
every import regardless of which DB it runs against. See
docs/content-pipeline-id-resolution-audit.md.

Idempotent: after a merge the ref is repointed at the curated target, so a
re-run resolves the jinaq id straight to the target (jinaq_uni.id ==
target) and is recognised as "already done".

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
from app.models.university_image import UniversityImage
from scripts.entity_resolver import repoint_jinaq_ref, resolve_jinaq_university

REVIEW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jinaq", "kz_university_merge_review.json")


async def _merge_one(db, *, jinaq_university_id: uuid.UUID, target_university_id: uuid.UUID, external_id: str) -> None:
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

    await repoint_jinaq_ref(db, external_id, target_university_id)

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


async def main(*, dry_run: bool) -> None:
    with open(REVIEW_PATH, encoding="utf-8") as f:
        review = json.load(f)

    async with async_session() as db:
        merged = skipped_not_confirmed = skipped_no_match = already_done = unresolved = renamed = 0

        for entry in review["entries"]:
            if entry.get("rename_to"):
                jinaq_uni = await resolve_jinaq_university(db, entry["jinaq_external_id"])
                if jinaq_uni is None:
                    continue
                jinaq_uni.name = entry["rename_to"]
                if entry.get("short_name_to"):
                    jinaq_uni.short_name = entry["short_name_to"]
                renamed += 1
                continue

            if not entry["confirmed"]:
                skipped_not_confirmed += 1
                continue
            if not entry["proposed_curated_match"]:
                skipped_no_match += 1
                continue

            target = (
                await db.execute(
                    select(University).where(University.slug == entry["proposed_curated_match"]["slug"])
                )
            ).scalar_one_or_none()
            if target is None:
                print(f"WARNING: target slug {entry['proposed_curated_match']['slug']!r} not found, skipping {entry['jinaq_name']!r}")
                continue

            jinaq_uni = await resolve_jinaq_university(db, entry["jinaq_external_id"])
            if jinaq_uni is None:
                print(f"  UNRESOLVED: jinaq external_id {entry['jinaq_external_id']} not on this DB — import_jinaq_universities.py must run first")
                unresolved += 1
                continue
            if jinaq_uni.id == target.id:
                already_done += 1
                continue

            print(f"merging {entry['jinaq_name']!r} (jinaq external_id={entry['jinaq_external_id']}) -> {entry['proposed_curated_match']['slug']!r} ({target.id})")
            await _merge_one(
                db,
                jinaq_university_id=jinaq_uni.id,
                target_university_id=target.id,
                external_id=entry["jinaq_external_id"],
            )
            await db.flush()
            merged += 1

        if dry_run:
            await db.rollback()
            print("[dry-run] no changes committed")
        else:
            await db.commit()

        print(
            f"Merged: {merged}, already done (idempotent skip): {already_done}, unresolved: {unresolved}, "
            f"renamed: {renamed}, not confirmed (left alone): {skipped_not_confirmed}, "
            f"confirmed no-match (left alone): {skipped_no_match}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
