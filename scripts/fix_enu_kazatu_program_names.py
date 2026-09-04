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

Rows are matched by (university slug, current program name) via
scripts/entity_resolver.py — NOT by a hardcoded Program.id, which is a
per-database random uuid4() that resolves to nothing on any other DB (this
script runs in start.sh / cd.yml on every fresh environment; see
docs/content-pipeline-id-resolution-audit.md). ЕНУ / КазАТУ each still have
a single row at this point in the pipeline (this runs before the jinaq
import and the jinaq→curated merge).

Dry-run by default -- prints every change, writes nothing. Pass --apply to
commit. Safe to re-run (renames are only applied if the row's name still
exactly matches the old, wrong value).

Run inside the api container:
  docker exec profy-backend-api-1 python scripts/fix_enu_kazatu_program_names.py [--apply]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.program import Program
from scripts.entity_resolver import resolve_program, resolve_university

# (university_slug, old_name_expected, new_name)
RENAMES = [
    # --- ENU (enu.kz/ru/page/applicants/bachelor) ---
    ("enu", "Филологический", "6B02307 Переводческое дело"),
    ("enu", "Международных отношений", "6B03102 Международные отношения"),
    ("enu", "Механико-математический", "6B05401 Математика"),
    ("enu", "Экономический", "6B04102 Экономика"),
    ("enu", "Информационных технологий", "6B06104 Вычислительная техника и программное обеспечение"),
    ("enu", "Транспортно-энергетический", "6B07118 Электроэнергетика"),
    ("enu", "Журналистики и политологии", "6B03204 Журналистика"),
    ("enu", "Юридический", "6B04201 Юриспруденция"),
    ("enu", "Архитектурно-строительный", "6B07322 Промышленное и гражданское строительство"),
    # --- KazATU (kazatu.edu.kz/edu-programs) ---
    ("kazatu", "Факультет ветеринарии и технологии животноводства", "6В09101 Ветеринарная безопасность"),
    ("kazatu", "Факультет компьютерных систем и профессионального образования", "Информационные системы и IT-решения по отраслям"),
    ("kazatu", "Факультет управления земельными ресурсами, архитектуры и дизайна", "5В042000 Архитектура"),
    ("kazatu", "Экономический факультет", "5В050600 Экономика"),
    ("kazatu", "Аграрный факультет", "Агрономия"),
    # split target: this row keeps Инженер-механик, renamed to Агроинженерия
    ("kazatu", "Приоритетные направления — сельскохозяйственное машиностроение и производство пищевых продуктов", "6B08701 Агроинженерия"),
]

# The split: after the rename above, this row must ALSO drop the
# "Технолог пищевого производства" direction (kept only "Инженер-механик"),
# and a new row is cloned for "Технолог пищевого производства" with its own
# real name.
SPLIT_SOURCE_UNIVERSITY_SLUG = "kazatu"
SPLIT_SOURCE_OLD_NAME = "Приоритетные направления — сельскохозяйственное машиностроение и производство пищевых продуктов"
SPLIT_SOURCE_NEW_NAME = "6B08701 Агроинженерия"
SPLIT_KEEP_DIRECTION = "inzhener-mehanik"
SPLIT_NEW_DIRECTION = "tehnolog-pischevogo-proizvodstva"
SPLIT_NEW_PROGRAM_NAME = "6B07201 Технология пищевых продуктов"


async def main() -> None:
    apply = "--apply" in sys.argv

    async with async_session() as db:
        renamed = 0
        skipped = 0
        university_cache: dict = {}

        async def _uni(slug: str):
            if slug not in university_cache:
                university_cache[slug], _ = await resolve_university(db, slug=slug)
            return university_cache[slug]

        for university_slug, old_name, new_name in RENAMES:
            university = await _uni(university_slug)
            program = await resolve_program(db, university=university, name=old_name) if university else None
            if program is None:
                # Either already renamed on a prior run, or the row doesn't
                # exist on this DB — both are safe no-ops.
                already = (
                    await resolve_program(db, university=university, name=new_name)
                    if university
                    else None
                )
                note = "already renamed" if already is not None else "not found"
                print(f"  - skip ({note}): {university_slug} | {old_name!r}")
                skipped += 1
                continue
            tag = "[updating]" if apply else "[would update]"
            print(f"{tag} {university_slug} | {old_name!r} -> {new_name!r}")
            if apply:
                program.name = new_name
            renamed += 1

        # --- the split ---
        split_uni = await _uni(SPLIT_SOURCE_UNIVERSITY_SLUG)
        source = None
        if split_uni is not None:
            # After the rename loop the row carries the new name (or still the
            # old one on a dry run / if the rename was skipped).
            for candidate_name in (SPLIT_SOURCE_NEW_NAME, SPLIT_SOURCE_OLD_NAME):
                source = await resolve_program(db, university=split_uni, name=candidate_name)
                if source is not None:
                    break
            if source is not None:
                await db.refresh(source, ["directions"])

        split_done = False
        if source is not None:
            dir_slugs = {d.slug for d in source.directions}
            if SPLIT_NEW_DIRECTION in dir_slugs:
                keep_dir = next(d for d in source.directions if d.slug == SPLIT_KEEP_DIRECTION)
                new_dir = next(d for d in source.directions if d.slug == SPLIT_NEW_DIRECTION)

                tag = "[splitting]" if apply else "[would split]"
                print(
                    f"{tag} {SPLIT_SOURCE_UNIVERSITY_SLUG}/{source.name!r}: detach {SPLIT_NEW_DIRECTION!r}, "
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
                print("  - split already applied or directions drifted, skipping split step")
        else:
            print("  - split source row not found, skipping split step")

        print(f"\n{renamed} renamed, {skipped} skipped (already fixed / absent). Split {'applied' if split_done and apply else ('would apply' if split_done else 'skipped')}.")

        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
