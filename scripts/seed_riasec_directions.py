"""
Seed script: populate the directions table from riasec_professions.py.
Run inside Docker: docker-compose exec api python scripts/seed_riasec_directions.py

Idempotent, self-healing: dedupes PROFESSIONS by title (first occurrence in
source order wins — this is what deterministically resolves the one real
data conflict in the source, "Psychologist" listed as both IES and SEI, see
riasec_professions.py's docstring), slugifies the `ru` title, upserts by
`slug`, deletes any DB row whose `slug` is no longer produced by the current
list.

Localized (KZ-306, single-row redesign): one direction = one row, keyed by
`slug` (always derived from the `ru` title — locale-invariant, career matching
and the profession↔program map never see a per-locale slug). `name` is a
`{"ru": ..., "kk": ...}` map (`ru` title + `riasec_professions.KK_NAMES`);
`description` and the JSONB lists are filled by `apply_direction_content.py`,
never here.

O*NET 6-dim vectors (PRO-385): loaded from
`scripts/data/our_professions_onet_riasec.json` by `ru` title and written to
`Direction.onet_vector`. Titles absent from that file keep NULL and use the
legacy code-based fallback at match time.

To change the profession catalog: edit riasec_professions.py and rerun this
script — nothing else hardcodes profession names or codes. To refresh
vectors: replace the JSON and rerun.
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.direction import Direction
from app.services.admin_lock import has_overrides, sync_fields
from scripts.riasec_professions import KK_NAMES, PROFESSIONS

_LOCALIZED_FIELDS = frozenset({"name"})
_ONET_VECTORS_PATH = Path(__file__).resolve().parent / "data" / "our_professions_onet_riasec.json"


def _load_onet_vectors() -> dict[str, dict[str, float]]:
    raw = json.loads(_ONET_VECTORS_PATH.read_text(encoding="utf-8"))
    return {entry["title"]: entry["vec"] for entry in raw}


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


def _name_map(title: str) -> dict:
    name = {"ru": title}
    kk = KK_NAMES.get(title)
    if kk:
        name["kk"] = kk
    return name


async def main() -> None:
    directions = dedupe_by_title(PROFESSIONS)
    live_slugs = {d["slug"] for d in directions}
    onet_vectors = _load_onet_vectors()

    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        existing_result = await db.execute(select(Direction))
        existing_by_slug = {d.slug: d for d in existing_result.scalars().all()}

        for data in directions:
            vector = onet_vectors.get(data["title"])
            existing = existing_by_slug.get(data["slug"])
            if existing is not None:
                changed = sync_fields(
                    existing,
                    {
                        "name": _name_map(data["title"]),
                        "holland_code": data["holland_code"],
                        "onet_vector": vector,
                    },
                    localized_fields=_LOCALIZED_FIELDS,
                )
                updated += changed
                skipped += not changed
                continue

            # description/professions/skills_needed/subjects_to_develop/
            # first_steps are left at the model's defaults (empty `ru`-only
            # maps) — filled in by apply_direction_content.py, which requires
            # the row to already exist.
            db.add(Direction(
                name=_name_map(data["title"]),
                slug=data["slug"],
                holland_code=data["holland_code"],
                onet_vector=vector,
            ))
            inserted += 1

        for slug, direction in existing_by_slug.items():
            if slug not in live_slugs and not has_overrides(direction):
                await db.delete(direction)
                deleted += 1

        await db.commit()
        with_vector = sum(1 for d in directions if d["title"] in onet_vectors)
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(
            f"Directions: {len(directions)} logical (deduped from "
            f"{len(PROFESSIONS)} raw rows); "
            f"onet_vector: {with_vector}, fallback (NULL): {len(directions) - with_vector}"
        )


if __name__ == "__main__":
    asyncio.run(main())
