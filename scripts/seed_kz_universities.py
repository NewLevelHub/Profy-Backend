"""
Seed script: populate universities/programs from the university-data/*.py
scrape (55 real KZ universities: Almaty + Astana).

Run inside Docker: docker-compose exec api python scripts/seed_kz_universities.py

Idempotent: upserts University by slug (already present in the source data).
A dozen of these universities are already seeded by scripts/seed_universities.py
under a different, hand-written English name — LEGACY_NAME_BY_SLUG reconciles
those so re-running this script attaches the richer specialty data to the
existing row (and backfills its slug) instead of creating a duplicate.

One Program row is created per INDIVIDUAL specialty (e.g. "Дизайн",
"Биотехнология"), not per specialty group. An earlier version created one
Program per group and classified the whole group at once — that broke down
hard whenever a "group" in the source data wasn't actually a cohesive unit:
some universities list their entire faculty index (agriculture + veterinary
+ economics + IT, unrelated fields) as a single "group", so any one-shot
classification of the group (by name, or by voting across its unrelated
members) was closer to a coin flip than a real answer. Classifying each
specialty on its own name removes that failure mode entirely — a name like
"Дизайн" or "Биотехнология" is unambiguous on its own, whereas concatenating
it with seven unrelated faculty names never was. See CLEANUP_ below for the
one-time migration that removes the old group-level rows.
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


def _cleanup_legacy_group_names(record: dict) -> set[str]:
    """Reproduces just enough of the old group-level naming to find and
    delete rows from before this migration — not used for anything else.
    Covers both the raw group name and the old comma-joined synthesized
    name for universities whose group label was a generic placeholder."""
    generic = {
        "направления", "факультеты", "факультеты / направления",
        "факультеты и направления", "программы",
    }
    names = set()
    for group in record.get("specialties", []):
        group_name = group["group"]
        names.add(group_name)
        if group_name.strip().lower() in generic:
            parts: list[str] = []
            length = 0
            for name in group["programs"]:
                if parts and length + len(name) > 150:
                    break
                parts.append(name)
                length += len(name)
            suffix = " и др." if len(parts) < len(group["programs"]) else ""
            names.add(", ".join(parts) + suffix)
    return names


async def main() -> None:
    async with async_session() as db:
        uni_inserted = uni_updated = uni_skipped = 0
        prog_inserted = prog_updated = prog_skipped = prog_deleted = 0
        unresolved: list[str] = []

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

            specialty_names = {
                name for group in record.get("specialties", []) for name in group["programs"]
            }
            legacy_names = _cleanup_legacy_group_names(record) - specialty_names
            if legacy_names:
                result = await db.execute(
                    select(Program).where(
                        Program.university_id == existing_uni.id,
                        Program.name.in_(legacy_names),
                    )
                )
                for stale in result.scalars().all():
                    await db.delete(stale)
                    prog_deleted += 1

            admission_notes = record.get("admission_requirements", [])

            for group in record.get("specialties", []):
                group_name = group["group"]
                for specialty_name in group["programs"]:
                    category_slug, confident = categorize(specialty_name)
                    if not confident:
                        unresolved.append(f"{record['name']} / {group_name} / {specialty_name}")

                    prog_data = {
                        "direction_slug": category_slug,
                        "language": "Казахский/Русский",
                        "cost_per_year": None,
                        "description": group_name,
                        "who_its_for": None,
                        "career_options": [],
                        "requirements": {"notes": admission_notes},
                        "deadlines": {},
                        "grants": [],
                    }

                    result = await db.execute(
                        select(Program).where(
                            Program.university_id == existing_uni.id,
                            Program.name == specialty_name,
                        )
                    )
                    existing_prog = result.scalar_one_or_none()

                    if existing_prog is None:
                        db.add(Program(university_id=existing_uni.id, name=specialty_name, **prog_data))
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
        f"Programs (individual specialties) — inserted: {prog_inserted}, "
        f"updated: {prog_updated}, skipped: {prog_skipped}, "
        f"stale group-level rows deleted: {prog_deleted}."
    )
    if unresolved:
        print(
            f"\n{len(unresolved)} specialty(ies) fell back to the default category "
            f"({categorize.__module__}.DEFAULT_CATEGORY) — review "
            f"scripts/specialty_category_lookup.py keywords:"
        )
        for name in unresolved:
            print(f"  - {name}")


if __name__ == "__main__":
    asyncio.run(main())
