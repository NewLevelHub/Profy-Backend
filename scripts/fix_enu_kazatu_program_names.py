"""
One-off fix for the ЕНУ (L.N. Gumilyov Eurasian National University, ovpo
013) / КазАТУ (Kazakh Agrotechnical Research University, ovpo 002)
faculty-name bug flagged in university-cards-ux-fix-plan.md §5 and
docs/university-module-fix-plan.md A2: unlike the cluster-seed bug
(program_name = direction.name), these two universities' Program.name holds
a FACULTY name (e.g. "Транспортно-энергетический") from a different,
earlier scrape, not the profession name and not a real specialty.

Real specialty names + classifier codes verified directly against each
university's own admissions pages (enu.kz/ru/page/applicants/bachelor,
kazatu.edu.kz/edu-programs and individual edu-program pages) via live web
search/fetch this session — not guessed.

KazATU had one row ('Приоритетные направления — сельскохозяйственное
машиностроение и производство пищевых продуктов') incorrectly serving TWO
distinct professions (Инженер-механик, Технолог пищевого производства) with
one vague combined name — real KazATU data has two separate specialties for
these (Агроинженерия vs Технология пищевых продуктов), so that row is SPLIT:
renamed to cover just one direction, and a new row cloned for the other.

Dry-run by default -- prints every change, writes nothing. Pass --apply to
commit. Safe to re-run (renames are only applied if the row's name still
exactly matches the old, wrong value).

Run inside the api container:
  docker exec profy-backend-api-1 python scripts/fix_enu_kazatu_program_names.py [--apply]
"""
import asyncio
import os
import sys
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.direction import Direction
from app.models.program import Program

# (program_id, old_name_expected, new_name)
RENAMES = [
    # --- ENU (enu.kz/ru/page/applicants/bachelor) ---
    ("3f50e442-7490-4fbe-8158-58fe2c34cdcf", "Филологический", "6B02307 Переводческое дело"),
    ("61673d37-3b2b-415c-9a92-d9c70adcaa17", "Международных отношений", "6B03102 Международные отношения"),
    ("8b0cab3c-704e-4229-97b2-e6efb908a9c2", "Механико-математический", "6B05401 Математика"),
    ("a354ad8e-879a-436f-bb59-db3b9d819767", "Экономический", "6B04102 Экономика"),
    ("bcce0549-3c90-4222-a4e3-df2ce34fb233", "Информационных технологий", "6B06104 Вычислительная техника и программное обеспечение"),
    ("bfa65f15-6cd5-4b85-874a-6a1d103c5ed8", "Транспортно-энергетический", "6B07118 Электроэнергетика"),
    ("d0d6335b-6b81-4629-af0c-06092135ccf4", "Журналистики и политологии", "6B03204 Журналистика"),
    ("da8b10a1-f756-4bb0-b964-360dad3224cb", "Юридический", "6B04201 Юриспруденция"),
    ("e999fcc8-b044-4cbb-8a49-35d86ed6dbee", "Архитектурно-строительный", "6B07322 Промышленное и гражданское строительство"),
    # --- KazATU (kazatu.edu.kz/edu-programs) ---
    ("021dae4d-81b2-4fcd-8e4a-53fc6ab03533", "Факультет ветеринарии и технологии животноводства", "6В09101 Ветеринарная безопасность"),
    ("103c21ac-7b0c-4af2-8b00-edf2e8ac0cf5", "Факультет компьютерных систем и профессионального образования", "Информационные системы и IT-решения по отраслям"),
    ("77667e71-ffc8-44d9-bc6a-a1d465e15218", "Факультет управления земельными ресурсами, архитектуры и дизайна", "5В042000 Архитектура"),
    ("7e7abb00-f4d6-4288-b14a-1d3a3e4d546a", "Экономический факультет", "5В050600 Экономика"),
    ("e46436d6-5439-4728-8c8a-b83de8d3f9ef", "Аграрный факультет", "Агрономия"),
    # split target: this row keeps Инженер-механик, renamed to Агроинженерия
    ("d5ac9d0f-f408-4a4a-8100-c4f2f33bc06b", "Приоритетные направления — сельскохозяйственное машиностроение и производство пищевых продуктов", "6B08701 Агроинженерия"),
]

# The split: after the rename above, this row must ALSO drop the
# "Технолог пищевого производства" direction (kept only "Инженер-механик"),
# and a new row is cloned for "Технолог пищевого производства" with its own
# real name.
SPLIT_SOURCE_PROGRAM_ID = "d5ac9d0f-f408-4a4a-8100-c4f2f33bc06b"
SPLIT_KEEP_DIRECTION = "inzhener-mehanik"
SPLIT_NEW_DIRECTION = "tehnolog-pischevogo-proizvodstva"
SPLIT_NEW_PROGRAM_NAME = "6B07201 Технология пищевых продуктов"


async def main() -> None:
    apply = "--apply" in sys.argv

    async with async_session() as db:
        renamed = 0
        skipped = 0

        for program_id, old_name, new_name in RENAMES:
            program = await db.get(Program, uuid.UUID(program_id))
            if program is None:
                print(f"  ! program not found: {program_id}")
                continue
            if program.name != old_name:
                print(f"  - skip (already changed or name drifted): {program_id} current={program.name!r}")
                skipped += 1
                continue
            tag = "[updating]" if apply else "[would update]"
            print(f"{tag} {program_id} | {old_name!r} -> {new_name!r}")
            if apply:
                program.name = new_name
            renamed += 1

        # --- the split ---
        source = await db.get(
            Program, uuid.UUID(SPLIT_SOURCE_PROGRAM_ID), options=[selectinload(Program.directions)]
        )
        split_done = False
        if source is not None and source.name == SPLIT_SOURCE_PROGRAM_ID:
            pass  # unreachable, just defensive
        if source is not None:
            dir_slugs = {d.slug for d in source.directions}
            if SPLIT_NEW_DIRECTION in dir_slugs:
                keep_dir = next(d for d in source.directions if d.slug == SPLIT_KEEP_DIRECTION)
                new_dir = next(d for d in source.directions if d.slug == SPLIT_NEW_DIRECTION)

                tag = "[splitting]" if apply else "[would split]"
                print(
                    f"{tag} {SPLIT_SOURCE_PROGRAM_ID}: detach {SPLIT_NEW_DIRECTION!r}, "
                    f"clone into new Program {SPLIT_NEW_PROGRAM_NAME!r}"
                )
                if apply:
                    source.directions = [keep_dir]
                    new_program = Program(
                        university_id=source.university_id,
                        name=SPLIT_NEW_PROGRAM_NAME,
                        language=source.language,
                        cost_per_year=source.cost_per_year,
                        cost_label=source.cost_label,
                        cost_per_year_min=source.cost_per_year_min,
                        cost_per_year_max=source.cost_per_year_max,
                        cost_currency=source.cost_currency,
                        description=source.description,
                        who_its_for=source.who_its_for,
                        career_options=list(source.career_options or []),
                        requirements=dict(source.requirements or {}),
                        deadlines=dict(source.deadlines or {}),
                        grants=list(source.grants or []),
                        source_url=source.source_url,
                    )
                    new_program.directions = [new_dir]
                    db.add(new_program)
                split_done = True
            else:
                print(f"  - split already applied or directions drifted, skipping split step")

        print(f"\n{renamed} renamed, {skipped} skipped (already fixed). Split {'applied' if split_done and apply else ('would apply' if split_done else 'skipped')}.")

        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
