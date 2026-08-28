"""
Nulls out Program.description for rows that were seeded with a fake
description by the pre-fix scripts/seed_kz_universities.py: instead of a real
per-program description, that script wrote `program.description = group_name`
— the specialty-GROUP/faculty label the program was filed under (e.g. "Школа
медицины и педиатрии"), not a real description of the program itself. See
university-cards-ux-fix-plan.md §7 and docs/university-module-fix-plan.md A3.

seed_kz_universities.py itself has since been fixed to leave
`program.description = None` for newly-seeded/updated rows (so the existing
ProgramListSection.tsx frontend fallback to university.description kicks in
regardless of the >40-char heuristic that let long group labels slip through
as if they were real descriptions). This script is the one-time cleanup for
rows that were already written with the old, wrong value before that fix.

Precision, not a blanket wipe: this rebuilds the exact (university, specialty)
-> group_name mapping the seed script used, straight from the same
university-data/*.py source files and the same _find_university() matching
logic (ovpo_code -> slug -> legacy name -> name), imported directly from
scripts.seed_kz_universities so there is no risk of the mapping drifting from
what actually got written. A Program row is only touched if:
  - it belongs to one of the universities in ALL_UNIVERSITIES (Almaty +
    Astana + missing-KZ source files — the only universities
    seed_kz_universities.py ever wrote a description for), AND
  - its current description is an EXACT match for the group_name its own
    specialty was filed under in that source data.
Any program with a real, different description (whether from a different
seed path or hand-edited later) is left untouched.

Dry-run by default — prints every row that would change, does not write
anything. Pass --apply to actually UPDATE the database.

Run inside the api container:
  docker exec profy-backend-api-1 python scripts/backfill_kz_program_description.py [--apply]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "university-data"))

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from scripts.seed_kz_universities import ALL_UNIVERSITIES, _find_university
from scripts.specialty_profession_map import GARBAGE_SPECIALTIES


async def main() -> None:
    apply = "--apply" in sys.argv

    async with async_session() as db:
        changed = 0
        checked = 0
        missing_universities: list[str] = []

        for record in ALL_UNIVERSITIES:
            uni = await _find_university(db, record)
            if uni is None:
                missing_universities.append(f"{record['name']} ({record.get('ovpo_code')})")
                continue

            # Same dedup-by-normalized-name and GARBAGE_SPECIALTIES skip as
            # seed_kz_universities.py, so we only build expectations for
            # specialties that actually got a Program row written for them.
            seen_specialty_names: set[str] = set()
            for group in record.get("specialties", []):
                group_name = group["group"]
                for specialty_name in group["programs"]:
                    if specialty_name in GARBAGE_SPECIALTIES:
                        continue
                    normalized_name = specialty_name.strip().lower()
                    if normalized_name in seen_specialty_names:
                        continue
                    seen_specialty_names.add(normalized_name)

                    result = await db.execute(
                        select(Program).where(
                            Program.university_id == uni.id,
                            Program.name_normalized == normalized_name,
                        )
                    )
                    prog = result.scalar_one_or_none()
                    if prog is None:
                        continue

                    checked += 1
                    if prog.description == group_name:
                        changed += 1
                        print(
                            f"{'[would update]' if not apply else '[updating]'} "
                            f"{uni.name!r} / {prog.name!r}: description "
                            f"{prog.description!r} -> None"
                        )
                        if apply:
                            prog.description = None

        print(f"\n{changed} of {checked} matched programs would have description nulled.")
        if missing_universities:
            print(
                f"\n{len(missing_universities)} source universities not found in the DB "
                f"(skipped, not an error — likely just not seeded yet):"
            )
            for name in missing_universities:
                print(f"  - {name}")

        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
