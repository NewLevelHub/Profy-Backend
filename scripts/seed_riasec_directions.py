"""
Seed script: populate the directions table from riasec_professions.py.
Run inside Docker: docker-compose exec api python scripts/seed_riasec_directions.py

Idempotent, self-healing: dedupes PROFESSIONS by title (first occurrence in
source order wins — this is what deterministically resolves the one real
data conflict in the source, "Psychologist" listed as both IES and SEI, see
riasec_professions.py's docstring), slugifies the `ru` title, upserts by
`(slug, locale)`, deletes any DB row whose `(slug, locale)` is no longer
produced by the current list *for that locale*.

Localized (KZ-301/KZ-306): one direction = one row per locale, keyed
`(slug, locale)`. `slug` (always derived from the `ru` title) and
`holland_code` are identical across locales — career matching and the
profession↔program map never see a per-locale slug. Only `name` differs here
(`ru` title vs `riasec_professions.KK_NAMES`); `description` and the JSONB
lists are filled per-locale by `apply_direction_content.py`, never here.

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
from scripts.riasec_professions import KK_NAMES, LOCALES, PROFESSIONS


_CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

_NAME_BY_LOCALE = {
    "ru": lambda title: title,
    "kk": lambda title: KK_NAMES[title],
}


def slugify(title: str) -> str:
    slug = title.lower()
    slug = slug.replace("&", " and ")
    slug = "".join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def dedupe_by_title(professions: list[dict]) -> list[dict]:
    """[{title, slug, holland_code}] — first occurrence of a title wins."""
    seen: dict[str, dict] = {}
    for entry in professions:
        title = entry["title"]
        if title in seen:
            continue
        seen[title] = {
            "title": title,
            "slug": slugify(title),
            "holland_code": entry["holland_code"],
        }
    return list(seen.values())


async def main() -> None:
    directions = dedupe_by_title(PROFESSIONS)
    live_slugs = {d["slug"] for d in directions}

    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        for locale in LOCALES:
            name_of = _NAME_BY_LOCALE[locale]

            existing_result = await db.execute(
                select(Direction).where(Direction.locale == locale)
            )
            existing_by_slug = {d.slug: d for d in existing_result.scalars().all()}

            for data in directions:
                name = name_of(data["title"])
                existing = existing_by_slug.get(data["slug"])
                if existing is not None:
                    changed = False
                    if existing.name != name:
                        existing.name = name
                        changed = True
                    if existing.holland_code != data["holland_code"]:
                        existing.holland_code = data["holland_code"]
                        changed = True
                    updated += changed
                    skipped += not changed
                    continue

                db.add(Direction(
                    name=name,
                    slug=data["slug"],
                    holland_code=data["holland_code"],
                    locale=locale,
                ))
                inserted += 1

            for slug, direction in existing_by_slug.items():
                if slug not in live_slugs:
                    await db.delete(direction)
                    deleted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(
            f"Directions: {len(directions)} logical (deduped from "
            f"{len(PROFESSIONS)} raw rows) x locales {LOCALES}"
        )


if __name__ == "__main__":
    asyncio.run(main())
