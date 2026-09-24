"""Export the `slug -> {ru name, kk name}` direction glossary (KZ-306).

KZ-401's Kazakh AI generation must use the exact catalog spelling of every
profession name, so the prompt builder / validator reads this file. Regenerate
it after any change to `riasec_professions.py` (names) or a re-seed:

    docker compose exec api python scripts/export_direction_glossary.py

Sourced from the DB `directions` table (post-seed truth), so it also reflects
the title-dedupe. Output: scripts/data/direction_glossary_kk.json —
`[{slug, holland_code, name_ru, name_kk}]`, sorted by slug.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.direction import Direction

OUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "direction_glossary_kk.json"
)


async def main() -> None:
    async with async_session() as db:
        rows = (await db.execute(select(Direction))).scalars().all()

    by_slug: dict[str, dict] = {}
    for d in rows:
        entry = by_slug.setdefault(
            d.slug, {"slug": d.slug, "holland_code": d.holland_code, "name_ru": None, "name_kk": None}
        )
        entry[f"name_{d.locale}"] = d.name

    glossary = [by_slug[s] for s in sorted(by_slug)]
    missing_kk = [e["slug"] for e in glossary if not e["name_kk"]]

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(glossary, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print(f"Wrote {len(glossary)} directions to {os.path.relpath(OUT_PATH)}")
    if missing_kk:
        print(f"WARNING: {len(missing_kk)} directions have no kk name: {missing_kk}")


if __name__ == "__main__":
    asyncio.run(main())
