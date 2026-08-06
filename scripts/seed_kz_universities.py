"""
Seed script: populate universities/programs from the university-data/*.py
scrape (55 real KZ universities: Almaty + Astana), tagging each specialty
group with one of the ~10 program categories via
scripts/specialty_category_lookup.py.

Run inside Docker: docker-compose exec api python scripts/seed_kz_universities.py

Idempotent: upserts University by slug (already present in the source data).
A dozen of these universities are already seeded by scripts/seed_universities.py
under a different, hand-written English name — LEGACY_NAME_BY_SLUG reconciles
those so re-running this script attaches the richer specialty data to the
existing row (and backfills its slug) instead of creating a duplicate.

One Program row is created per specialty group (e.g. "Информационные
технологии и кибербезопасность"), not per individual program name inside it —
that group already carries the keywords scripts/specialty_category_lookup.py
classifies on, and Program.career_options is exactly where the individual
program names belong.
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "university-data"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from scripts.specialty_category_lookup import categorize

from almaty_universities_data import ALMATY_UNIVERSITIES
from astana_universities_data import ASTANA_UNIVERSITIES

ALL_UNIVERSITIES: list[dict] = ALMATY_UNIVERSITIES + ASTANA_UNIVERSITIES

# slug (from university-data/*.py) -> exact University.name already seeded by
# scripts/seed_universities.py. Prevents duplicating universities both scripts
# know about under two different name spellings.
LEGACY_NAME_BY_SLUG: dict[str, str] = {
    "nazarbayev-university": "Nazarbayev University",
    "universitet-kimep": "KIMEP University",
    "kazahskij-naczionalnyj-universitet-im-al-farabi": "Al-Farabi Kazakh National University",
    "aitu": "Astana IT University",
    "kazahskaya-naczionalnaya-akademiya-iskusstv": "Kazakh National Academy of Arts named after T. Zhurgenov",
    "satbayev-university": "Satbayev University",
    "enu": "L.N. Gumilyov Eurasian National University",
    "kazahskij-naczionalnyj-pedagogicheskij-universitet-im-abaya": "Abai Kazakh National Pedagogical University",
    "mnu": "M. Narikbayev KAZGUU University",
    "kazahskij-universitet-mezhdunarodnyh-otnoshenij-i-mirovyh-yazykov": (
        "Kazakh Ablai Khan University of International Relations and World Languages"
    ),
    "almaty-menedzhment-universitet-amu": "Almaty Management University",
    "universitet-narhoz": "Narxoz University",
}


async def _find_university(db: AsyncSession, record: dict) -> University | None:
    result = await db.execute(select(University).where(University.slug == record["slug"]))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    legacy_name = LEGACY_NAME_BY_SLUG.get(record["slug"])
    if legacy_name is not None:
        result = await db.execute(select(University).where(University.name == legacy_name))
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

    result = await db.execute(select(University).where(University.name == record["name"]))
    return result.scalar_one_or_none()


async def main() -> None:
    async with async_session() as db:
        uni_inserted = uni_updated = uni_skipped = 0
        prog_inserted = prog_updated = prog_skipped = 0
        unresolved_groups: list[str] = []

        for record in ALL_UNIVERSITIES:
            existing_uni = await _find_university(db, record)

            if existing_uni is None:
                existing_uni = University(
                    name=record["name"],
                    slug=record["slug"],
                    country=record["country"],
                    city=record["city"],
                    website=record.get("website"),
                    ranking=None,
                    description=record.get("specialties_summary") or "",
                )
                db.add(existing_uni)
                await db.flush()
                uni_inserted += 1
            else:
                changed = False
                if not existing_uni.slug:
                    existing_uni.slug = record["slug"]
                    changed = True
                if not existing_uni.description and record.get("specialties_summary"):
                    existing_uni.description = record["specialties_summary"]
                    changed = True
                if changed:
                    uni_updated += 1
                else:
                    uni_skipped += 1

            for group in record.get("specialties", []):
                group_name = group["group"]
                program_names = group["programs"]
                category_slug, confident = categorize(group_name, program_names)
                if not confident:
                    unresolved_groups.append(f"{record['name']} / {group_name}")

                prog_data = {
                    "direction_slug": category_slug,
                    "language": "Казахский/Русский",
                    "cost_per_year": None,
                    "description": ", ".join(program_names),
                    "who_its_for": None,
                    "career_options": program_names,
                    "requirements": {"notes": record.get("admission_requirements", [])},
                    "deadlines": {},
                    "grants": [],
                }

                result = await db.execute(
                    select(Program).where(
                        Program.university_id == existing_uni.id,
                        Program.name == group_name,
                    )
                )
                existing_prog = result.scalar_one_or_none()

                if existing_prog is None:
                    db.add(Program(university_id=existing_uni.id, name=group_name, **prog_data))
                    prog_inserted += 1
                else:
                    changed = False
                    for field, value in prog_data.items():
                        if getattr(existing_prog, field) != value:
                            setattr(existing_prog, field, value)
                            changed = True
                    if changed:
                        prog_updated += 1
                    else:
                        prog_skipped += 1

        await db.commit()

    print(
        f"Universities — inserted: {uni_inserted}, updated: {uni_updated}, "
        f"skipped: {uni_skipped}. Total in source: {len(ALL_UNIVERSITIES)}"
    )
    print(
        f"Programs (specialty groups) — inserted: {prog_inserted}, "
        f"updated: {prog_updated}, skipped: {prog_skipped}."
    )
    if unresolved_groups:
        print(
            f"\n{len(unresolved_groups)} specialty group(s) fell back to the default "
            f"category ({categorize.__module__}.DEFAULT_CATEGORY) — review "
            f"scripts/specialty_category_lookup.py keywords:"
        )
        for name in unresolved_groups:
            print(f"  - {name}")


if __name__ == "__main__":
    asyncio.run(main())
