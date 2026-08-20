"""
scripts/seed_kz_universities.py wrote University.description from the source
data's `specialties_summary` field (e.g. "37-48 специальностей бакалавриата
на 8-9 факультетах.") instead of its `description` field (the actual prose
blurb, e.g. "Крупнейший аграрный вуз Центрального и Северного Казахстана...")
for every university it inserted — the two source keys got swapped in the
University(...) constructor and in the backfill-on-update branch. Fixed in
that script; this is the one-off backfill for rows it already wrote wrong.

Only overwrites University.description when it exactly equals the record's
specialties_summary (proof it was the buggy write, not a manually-edited or
differently-sourced description) — same "no blanket wipe" precision as
scripts/backfill_kazatu_duplicate_group_labels.py.

Dry-run by default. Pass --apply to commit.
  docker exec profi-backend-api-1 python scripts/backfill_university_description_summary_swap.py [--apply]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "university-data"))

from sqlalchemy import select

from app.database import async_session
from app.models.university import University

from almaty_universities_data import ALMATY_UNIVERSITIES
from astana_universities_data import ASTANA_UNIVERSITIES
from missing_kz_universities_data import MISSING_KZ_UNIVERSITIES

ALL_UNIVERSITIES: list[dict] = ALMATY_UNIVERSITIES + ASTANA_UNIVERSITIES + MISSING_KZ_UNIVERSITIES
BY_SLUG: dict[str, dict] = {r["slug"]: r for r in ALL_UNIVERSITIES}


async def main() -> None:
    apply = "--apply" in sys.argv

    async with async_session() as db:
        unis = (await db.execute(select(University))).scalars().all()

        changed = 0
        for u in unis:
            record = BY_SLUG.get(u.slug)
            if record is None:
                continue

            summary = (record.get("specialties_summary") or "").strip()
            real_description = (record.get("description") or "").strip()

            if not summary or not real_description or real_description == summary:
                continue
            if (u.description or "").strip() != summary:
                continue

            tag = "[updating]" if apply else "[would update]"
            print(f"{tag} {u.slug} ({u.id}):\n  old: {u.description!r}\n  new: {real_description!r}\n")
            if apply:
                u.description = real_description
            changed += 1

        print(f"\n{changed} universities {'updated' if apply else 'would be updated'}.")
        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
