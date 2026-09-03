"""Applies the human-reviewed output of generate_direction_content.py to the
`directions` table. Separate from generation on purpose — the user reviews
scripts/direction_content_review.json (or the published Artifact built from
it) before this script runs; generation itself never touches the DB.

Only ever writes description/skills_needed/subjects_to_develop/first_steps —
never touches name/slug/holland_code/professions (owned by
scripts/seed_riasec_directions.py).

Run inside Docker: docker compose exec api python scripts/apply_direction_content.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.direction import Direction
from app.services.admin_lock import sync_fields

REVIEW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "direction_content_review.json")


async def main() -> None:
    with open(REVIEW_PATH, encoding="utf-8") as f:
        reviewed = json.load(f)

    async with async_session() as db:
        result = await db.execute(select(Direction))
        by_slug = {d.slug: d for d in result.scalars().all()}

        updated = 0
        missing: list[str] = []

        for entry in reviewed:
            direction = by_slug.get(entry["slug"])
            if direction is None:
                missing.append(entry["slug"])
                continue

            # Guard against reverting an admin's PATCH /admin/directions/{id}
            # edit (app/services/admin_content_service.py::update_direction)
            # to these same 4 fields — same sync_fields() helper the 7
            # scripts/seed_*.py scripts use, see
            # docs/admin-questions-content-overrides-plan.md.
            changed = sync_fields(direction, {
                "description": entry["description"],
                "skills_needed": entry["skills_needed"],
                "subjects_to_develop": entry["subjects_to_develop"],
                "first_steps": entry["first_steps"],
            })
            if changed:
                updated += 1

        await db.commit()
        print(f"Done. Updated {updated}/{len(reviewed)} directions.")
        if missing:
            print(f"Slugs in review file but not found in DB (skipped): {missing}")


if __name__ == "__main__":
    asyncio.run(main())
