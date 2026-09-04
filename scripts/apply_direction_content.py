"""Applies the human-reviewed output of generate_direction_content.py to the
`directions` table. Separate from generation on purpose — the user reviews
scripts/direction_content_review.json (or the published Artifact built from
it) before this script runs; generation itself never touches the DB.

Only ever writes description/skills_needed/subjects_to_develop/first_steps —
never touches name/slug/holland_code/professions (owned by
scripts/seed_riasec_directions.py).

Localized (KZ-306): applies `direction_content_review.json` to `locale='ru'`
rows and, when present, `direction_content_review_kk.json` to `locale='kk'`
rows — keyed by `(slug, locale)`. A locale whose review file is absent is
skipped.

Transitional (KZ-306, until the kk content batch runs): after the `ru` pass,
any `kk` row still missing a `description` is bootstrapped from its `ru`
sibling's content, so a `kk` direction detail never renders a blank body. The
kk review file (once it exists) overwrites this with real translations. This
mirrors the KZ-501/502 "ru only" transitional-content idea.

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

_HERE = os.path.dirname(os.path.abspath(__file__))
# ordered: ru first, so the kk-from-ru bootstrap below sees fresh ru content,
# then the kk file (if present) overwrites it with real translations.
REVIEW_FILES = [
    ("ru", os.path.join(_HERE, "direction_content_review.json")),
    ("kk", os.path.join(_HERE, "direction_content_review_kk.json")),
]
_CONTENT_FIELDS = ("description", "skills_needed", "subjects_to_develop", "first_steps")


async def _apply_file(db, locale: str, path: str) -> None:
    if not os.path.exists(path):
        print(f"[{locale}] no review file ({os.path.basename(path)}) — skipped")
        return

    with open(path, encoding="utf-8") as f:
        reviewed = json.load(f)

    by_slug = {
        d.slug: d
        for d in (
            await db.execute(select(Direction).where(Direction.locale == locale))
        ).scalars()
    }

    updated = 0
    missing: list[str] = []
    for entry in reviewed:
        direction = by_slug.get(entry["slug"])
        if direction is None:
            missing.append(entry["slug"])
            continue
        # sync_fields (not raw setattr) so an admin PATCH /admin/directions/{id}
        # edit to these 4 fields survives a reseed — see
        # docs/admin-questions-content-overrides-plan.md.
        if sync_fields(direction, {field: entry[field] for field in _CONTENT_FIELDS}):
            updated += 1

    print(f"[{locale}] Updated {updated}/{len(reviewed)} directions.")
    if missing:
        print(f"[{locale}] Slugs in review file but not in DB (skipped): {missing}")


async def _bootstrap_kk_from_ru(db) -> None:
    rows = (await db.execute(select(Direction))).scalars().all()
    ru = {d.slug: d for d in rows if d.locale == "ru"}
    bootstrapped = 0
    for d in rows:
        if d.locale != "kk" or d.description:
            continue
        src = ru.get(d.slug)
        if src is None or not src.description:
            continue
        for field in _CONTENT_FIELDS:
            setattr(d, field, getattr(src, field))
        bootstrapped += 1
    if bootstrapped:
        print(f"[kk] Bootstrapped {bootstrapped} directions from ru (no kk content yet).")


async def main() -> None:
    async with async_session() as db:
        for locale, path in REVIEW_FILES:
            await _apply_file(db, locale, path)
        await _bootstrap_kk_from_ru(db)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
