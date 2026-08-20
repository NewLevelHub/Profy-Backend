"""
Follow-up to backfill_foreign_cost_numeric.py: ~10 (university, cost_label)
pairs the first pass missed because the same free-text label is shared
across programs whose University.name string doesn't exactly match what was
transcribed the first time round (e.g. "Politecnico di Milano" plain vs
"Politecnico di Milano — Scuola del Design" both carry the Design label on
some rows). Names here were re-read directly from the DB, not retyped from
memory, to avoid the same mismatch twice.

Dry-run by default. Pass --apply to commit.
  docker exec profy-backend-api-1 python scripts/backfill_foreign_cost_numeric_pass2.py [--apply]
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

NUMERIC: dict[tuple[str, str], tuple[str, float, float]] = {
    ("Københavns Universitet (University of Copenhagen), Faculty of Science", "€10 000–17 000 в год (60 ECTS) для студентов не из ЕС/ЕЭЗ/Швейцарии"): ("EUR", 10000, 17000),
    ("China Agricultural University", "≈ 26 000–35 000 китайских юаней (CNY) в год для магистерских программ иностранных студентов"): ("CNY", 26000, 35000),
    ("Politecnico di Milano", "€900-4,000 в год (в зависимости от программы и уровня дохода семьи)"): ("EUR", 900, 4000),
    ("TU Bergakademie Freiberg", "~97 EUR в семестр; магистерские программы англ.: €37,600-42,800 за 2 года"): ("EUR", 18800, 21400),
    ("Gubkin Russian State University of Oil and Gas", "~4,394 USD в год; ₽167,170 (бакалавриат), ₽364,500 (магистратура); +700 USD регистрация"): ("USD", 4394, 4394),
    ("Bandung Institute of Technology", "~USD 5,000-21,100 в год; IDR 42,000,000-46,500,000 в семестр (non-management/management programs)"): ("USD", 5000, 21100),
    ("University of Hohenheim", "~1 500 EUR в семестр для нерезидентов ЕС; ~174,50 EUR административные сборы"): ("EUR", 3000, 3000),
    ("Vaganova Academy of Russian Ballet", "~1 650 000 RUB (~18 000 USD) за 10-месячную программу"): ("USD", 18000, 18000),
    ("École Nationale Supérieure des Beaux-Arts", "€458 за семестр + €103 взнос CVEC + €56 взнос на конкурс (одна из самых доступных школ искусств)"): ("EUR", 1122, 1122),
}

TEXT_ONLY: dict[tuple[str, str], str] = {
    (
        "Indian Institute of Management Ahmedabad",
        "Для иностранных студентов — от ~5 млн INR за программу",
    ): "Для иностранных студентов — от ~5 млн INR за всю программу (не за год)",
}


async def main() -> None:
    apply = "--apply" in sys.argv

    async with async_session() as db:
        numeric_changed = 0
        text_changed = 0
        not_found = []

        for (uni_name, old_label), (currency, cmin, cmax) in NUMERIC.items():
            unis = (await db.execute(select(University).where(University.name == uni_name))).scalars().all()
            if not unis:
                not_found.append(f"university not found: {uni_name!r}")
                continue
            progs = (
                await db.execute(
                    select(Program).where(
                        Program.university_id.in_([u.id for u in unis]), Program.cost_label == old_label
                    )
                )
            ).scalars().all()
            if not progs:
                not_found.append(f"program not found: {uni_name!r} / {old_label[:60]!r}")
                continue
            for prog in progs:
                if prog.cost_per_year_min is not None:
                    continue
                tag = "[updating]" if apply else "[would update]"
                print(f"{tag} {uni_name} | {prog.name!r} | cost -> {currency} {cmin}-{cmax}")
                if apply:
                    prog.cost_currency = currency
                    prog.cost_per_year_min = cmin
                    prog.cost_per_year_max = cmax
                numeric_changed += 1

        for (uni_name, old_label), new_label in TEXT_ONLY.items():
            unis = (await db.execute(select(University).where(University.name == uni_name))).scalars().all()
            if not unis:
                not_found.append(f"university not found: {uni_name!r}")
                continue
            progs = (
                await db.execute(
                    select(Program).where(
                        Program.university_id.in_([u.id for u in unis]), Program.cost_label == old_label
                    )
                )
            ).scalars().all()
            if not progs:
                not_found.append(f"program not found: {uni_name!r} / {old_label[:60]!r}")
                continue
            for prog in progs:
                tag = "[updating]" if apply else "[would update]"
                print(f"{tag} {uni_name} | {prog.name!r} | text-only rewrite")
                if apply:
                    prog.cost_label = new_label
                text_changed += 1

        print(f"\n{numeric_changed} numeric updates, {text_changed} text-only updates.")
        if not_found:
            print(f"\n{len(not_found)} lookups failed:")
            for msg in not_found:
                print(f"  - {msg}")

        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
