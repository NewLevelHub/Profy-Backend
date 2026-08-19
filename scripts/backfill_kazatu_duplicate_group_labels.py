"""
KazATU (slug `kazatu`, ovpo 002) has a second, duplicate source record in
university-data/almaty_universities_data.py (slug
`kazahskij-agrotehnicheskij-universitet-kazatu`, city "Алматы" — the real
university is in Astana; see docs/university-module-fix-plan.md A1) whose
`_find_university()` lookup fails during scripts/backfill_kz_program_description.py
(no ovpo_code on that duplicate record, name doesn't fuzzy-match) — so that
backfill silently skips the 14 Program rows this duplicate record actually
seeded, and they keep their group-label description
("Инженерия и энергетика", "IT и телекоммуникации", etc.) instead of falling
back to University.description like every other KZ program does.

This is a narrower, targeted version of the same fix
(backfill_kz_program_description.py) for exactly those 14 rows — hardcoded
group labels because they're the fixed, closed set from that one duplicate
record (see almaty_universities_data.py's `kazahskij-agrotehnicheskij-universitet-kazatu`
entry). Only nulls description when it exactly equals a known group label —
same "no blanket wipe" precision as the general script.

Dry-run by default. Pass --apply to commit.
  docker exec profy-backend-api-1 python scripts/backfill_kazatu_duplicate_group_labels.py [--apply]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university import University

# Group labels from almaty_universities_data.py's
# "kazahskij-agrotehnicheskij-universitet-kazatu" duplicate record's
# `specialties` list — the only source that ever wrote these as
# Program.description for KazATU.
GROUP_LABELS = {
    "Инженерия и энергетика",
    "Животноводство и водные ресурсы",
    "Экология и природа",
    "Дизайн и финансы",
    "Логистика",
    "IT и телекоммуникации",
}


async def main() -> None:
    apply = "--apply" in sys.argv

    async with async_session() as db:
        uni = (await db.execute(select(University).where(University.slug == "kazatu"))).scalar_one_or_none()
        if uni is None:
            print("kazatu university not found — nothing to do.")
            return

        progs = (await db.execute(select(Program).where(Program.university_id == uni.id))).scalars().all()

        changed = 0
        for p in progs:
            if p.description in GROUP_LABELS:
                tag = "[updating]" if apply else "[would update]"
                print(f"{tag} {p.id} {p.name!r}: {p.description!r} -> None")
                if apply:
                    p.description = None
                changed += 1

        print(f"\n{changed} programs {'updated' if apply else 'would be updated'}.")
        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
