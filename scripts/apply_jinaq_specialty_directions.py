"""Applies the human-reviewed direction_slugs from
scripts/data/jinaq/specialty_direction_review.json to Program rows, by
exact normalized name match (not category, not fuzzy — per this project's
established rule against automatic specialty/profession tagging; the actual
tagging decisions were made by a human reviewing
scripts/draft_fill_specialty_directions.py's draft, this script only applies
what was approved).

Only touches Program rows whose `directions` is currently EMPTY — never
overwrites or removes directions a human already assigned via
scripts/specialty_profession_map.py. This also means it's not limited to
jinaq-sourced programs: any program (regardless of source) that happens to
share one of these specialty names and has no directions yet gets tagged
too — safe by construction, since "already tagged" is always left alone.

Idempotent: re-running only ever touches rows still empty at that time, so
it can't undo its own previous run or anyone else's tagging.

Run inside the api container:
  docker-compose exec api python scripts/apply_jinaq_specialty_directions.py [--dry-run]
"""
import argparse
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.direction import Direction
from app.models.program import Program

REVIEW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jinaq", "specialty_direction_review.json")


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


async def main(*, dry_run: bool) -> None:
    with open(REVIEW_PATH, encoding="utf-8") as f:
        review = json.load(f)

    mapping: dict[str, list[str]] = {
        _normalize(s["name"]): s["direction_slugs"] for s in review["specialties"] if s["direction_slugs"]
    }
    print(f"Loaded {len(mapping)} reviewed specialty -> direction_slugs mappings")

    async with async_session() as db:
        directions_result = await db.execute(select(Direction))
        direction_by_slug = {d.slug: d for d in directions_result.scalars().all()}

        programs_result = await db.execute(select(Program).options(selectinload(Program.directions)))
        programs = programs_result.scalars().all()

        updated = 0
        skipped_already_tagged = 0
        skipped_no_mapping = 0
        bad_slug_refs: set[str] = set()

        for program in programs:
            if program.directions:
                skipped_already_tagged += 1
                continue

            slugs = mapping.get(_normalize(program.name))
            if not slugs:
                skipped_no_mapping += 1
                continue

            resolved = []
            for slug in slugs:
                direction = direction_by_slug.get(slug)
                if direction is None:
                    bad_slug_refs.add(slug)
                    continue
                resolved.append(direction)

            if not resolved:
                continue

            program.directions = resolved
            updated += 1

        if dry_run:
            await db.rollback()
            print("[dry-run] no changes committed")
        else:
            await db.commit()

        print(
            f"Updated: {updated}, already tagged (left alone): {skipped_already_tagged}, "
            f"no mapping for this name: {skipped_no_mapping}"
        )
        if bad_slug_refs:
            print(f"WARNING: {len(bad_slug_refs)} referenced slugs don't exist in directions table: {bad_slug_refs}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
