"""
Idempotent update: fills in University.website (and, where researched,
city/location/short_name) for the ~47 universities that were seeded via
seed_92_professions_universities.py without these fields (that script only
ever populated ranking/ranking_label/description — see its docstring).

Source: scripts/data/university_enrichment_2027.json, hand-researched via web
search against each institution's own site (foreign universities) or 2GIS /
Wikipedia / the institution's own domain (Kazakhstani regional universities).

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/apply_university_enrichment_2027.py [--dry-run]
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

DATA_PATH = os.path.join(_ROOT, "scripts", "data", "university_enrichment_2027.json")

FIELDS = ("website", "city", "location", "short_name")


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    with open(DATA_PATH, encoding="utf-8") as f:
        updates: dict[str, dict] = json.load(f)

    async with async_session() as db:
        updated = 0
        unchanged = 0
        missing: list[str] = []

        for slug, payload in updates.items():
            result = await db.execute(select(University).where(University.slug == slug))
            university = result.scalar_one_or_none()
            if university is None:
                missing.append(slug)
                continue

            changes = {
                field: value
                for field, value in payload.items()
                if field in FIELDS and getattr(university, field) != value
            }

            if changes:
                updated += 1
                if dry_run:
                    print(f"[would update] {slug} -> {changes}")
                else:
                    for field, value in changes.items():
                        setattr(university, field, value)
            else:
                unchanged += 1

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}universities updated: {updated}, unchanged: {unchanged}, missing: {len(missing)}")
        if missing:
            print("Missing slugs (not found in DB):")
            for m in missing:
                print(f"  - {m}")


if __name__ == "__main__":
    asyncio.run(main())
