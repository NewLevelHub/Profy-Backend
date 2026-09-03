"""
Seed script: populate the directions table from riasec_professions.py.
Run inside Docker: docker-compose exec api python scripts/seed_riasec_directions.py

Idempotent, self-healing: dedupes PROFESSIONS by title (first occurrence in
source order wins — this is what deterministically resolves the one real
data conflict in the source, "Psychologist" listed as both IES and SEI, see
riasec_professions.py's docstring), slugifies the title, upserts by slug,
deletes any DB row whose slug is no longer produced by the current list.

To change the profession catalog: edit riasec_professions.py and rerun this
script — nothing else hardcodes profession names or codes.
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.direction import Direction
from app.services.admin_lock import has_overrides, sync_fields
from scripts.riasec_professions import PROFESSIONS


_CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(title: str) -> str:
    slug = title.lower()
    slug = slug.replace("&", " and ")
    slug = "".join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def dedupe_by_title(professions: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for entry in professions:
        title = entry["title"]
        if title in seen:
            continue
        seen[title] = {
            "name": title,
            "slug": slugify(title),
            "holland_code": entry["holland_code"],
        }
    return list(seen.values())


async def main() -> None:
    directions = dedupe_by_title(PROFESSIONS)

    async with async_session() as db:
        live_slugs = {d["slug"] for d in directions}

        existing_result = await db.execute(select(Direction))
        existing_by_slug = {d.slug: d for d in existing_result.scalars().all()}

        inserted = 0
        updated = 0
        skipped = 0
        deleted = 0

        for data in directions:
            existing = existing_by_slug.get(data["slug"])
            if existing is not None:
                changed = sync_fields(existing, {
                    "name": data["name"],
                    "holland_code": data["holland_code"],
                })
                if changed:
                    updated += 1
                else:
                    skipped += 1
                continue

            db.add(Direction(
                name=data["name"],
                slug=data["slug"],
                holland_code=data["holland_code"],
            ))
            inserted += 1

        for slug, direction in existing_by_slug.items():
            if slug not in live_slugs and not has_overrides(direction):
                await db.delete(direction)
                deleted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(f"Total directions (deduped from {len(PROFESSIONS)} raw rows): {len(directions)}")


if __name__ == "__main__":
    asyncio.run(main())
