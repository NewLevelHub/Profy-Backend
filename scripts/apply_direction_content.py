"""Applies the human-reviewed output of generate_direction_content.py to the
`directions` table. Separate from generation on purpose — the user reviews
scripts/direction_content_review.json (or the published Artifact built from
it) before this script runs; generation itself never touches the DB.

Only ever writes description/skills_needed/subjects_to_develop/first_steps —
never touches name/slug/holland_code/professions (owned by
scripts/seed_riasec_directions.py).

Localized (KZ-306, single-row redesign): one direction = one row (see
docs/i18n-contract.md §8). Applies `direction_content_review.json` into each
field's `"ru"` key and, when present, `direction_content_review_kk.json` into
`"kk"` — both keyed by `slug`. A locale whose review file is absent, or whose
review file has no entry for a given slug, simply leaves that key unset;
`app.i18n.pick_locale`/`pick_locale_list` fall back to `ru` at read time, so
there is no need for the transitional "bootstrap kk from ru" copy this script
used to do when kk lived in its own physical row.

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
# ru first: kk review coverage is currently a subset of ru's, so applying ru
# first means a slug present in both ends up with both keys regardless of
# dict/file order — order no longer matters for correctness (each locale only
# ever touches its own key of the field maps), kept for readable output order.
REVIEW_FILES = {
    "ru": os.path.join(_HERE, "direction_content_review.json"),
    "kk": os.path.join(_HERE, "direction_content_review_kk.json"),
}
_CONTENT_FIELDS = ("description", "skills_needed", "subjects_to_develop", "first_steps")
_CONTENT_FIELDS_SET = frozenset(_CONTENT_FIELDS)


def _load_reviewed(locale: str, path: str) -> dict[str, dict] | None:
    if not os.path.exists(path):
        print(f"[{locale}] no review file ({os.path.basename(path)}) — skipped")
        return None
    with open(path, encoding="utf-8") as f:
        reviewed = json.load(f)
    return {entry["slug"]: entry for entry in reviewed}


async def main() -> None:
    by_locale = {locale: _load_reviewed(locale, path) for locale, path in REVIEW_FILES.items()}
    if not any(by_locale.values()):
        return

    async with async_session() as db:
        directions = (await db.execute(select(Direction))).scalars().all()
        by_slug = {d.slug: d for d in directions}

        touched: set[str] = set()
        missing: dict[str, list[str]] = {}
        for locale, reviewed in by_locale.items():
            if reviewed is None:
                continue
            locale_missing = []
            for slug, entry in reviewed.items():
                direction = by_slug.get(slug)
                if direction is None:
                    locale_missing.append(slug)
                    continue
                # sync_fields (not raw setattr) so an admin PATCH
                # /admin/directions/{id} edit to these 4 fields survives a
                # reseed — see docs/admin-questions-content-overrides-plan.md.
                # Each field's bank value is the row's current map with just
                # this locale's key set from the review file — the other
                # locale's key (applied in a separate pass over `by_locale`)
                # is preserved as-is.
                updates = {
                    field: {**(getattr(direction, field) or {}), locale: entry[field]}
                    for field in _CONTENT_FIELDS
                }
                if sync_fields(direction, updates, localized_fields=_CONTENT_FIELDS_SET):
                    touched.add(slug)
            if locale_missing:
                missing[locale] = locale_missing

        await db.commit()
        print(f"Updated {len(touched)} direction(s) from {sum(1 for v in by_locale.values() if v)} review file(s).")
        for locale, slugs in missing.items():
            print(f"[{locale}] Slugs in review file but not in DB (skipped): {slugs}")


if __name__ == "__main__":
    asyncio.run(main())
