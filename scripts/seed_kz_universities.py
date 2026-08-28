"""
Seed script: populate universities/programs from the university-data/*.py
scrape (55 real KZ universities: Almaty + Astana) plus the 48 regional/branch
universities researched to close the gap documented in
docs/ovpo-registry-gap-analysis.md (university-data/missing_kz_universities_data.py,
see docs/university-module-fix-plan.md A3).

Run inside Docker: docker-compose exec api python scripts/seed_kz_universities.py

Idempotent: upserts University by ovpo_code when the data entry has one (the
canonical key per docs/university-module-fix-plan.md A1 — official MOН РК
registry identifier, doesn't drift the way names do), falling back to slug.
A dozen of these universities are already seeded by scripts/seed_universities.py
under a different, hand-written English name — LEGACY_NAME_BY_SLUG reconciles
those so re-running this script attaches the richer specialty data to the
existing row (and backfills its slug) instead of creating a duplicate.

One Program row is created per INDIVIDUAL specialty (e.g. "Дизайн",
"Биотехнология"), tagged with the profession(s) it actually trains someone
for via scripts/specialty_profession_map.py — a hand-curated direct mapping,
not an inferred category. Two earlier versions (one Program per specialty
GROUP classified as a whole; then one per specialty but classified by
keyword/category) both produced confidently wrong matches in practice — a
shared category is not the same thing as a real profession match. Entries in
GARBAGE_SPECIALTIES (partner-university names listed as if they were
programs, purely administrative units, faculty labels with no specific
subject) are skipped entirely, not force-fit into anything.
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
from app.models.direction import Direction
from app.models.program import Program
from app.models.university import University
from scripts.specialty_profession_map import GARBAGE_SPECIALTIES, SPECIALTY_TO_PROFESSIONS

from almaty_universities_data import ALMATY_UNIVERSITIES
from astana_universities_data import ASTANA_UNIVERSITIES
from missing_kz_universities_data import MISSING_KZ_UNIVERSITIES

ALL_UNIVERSITIES: list[dict] = ALMATY_UNIVERSITIES + ASTANA_UNIVERSITIES + MISSING_KZ_UNIVERSITIES

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

# Overrides the blanket "Казахский, Русский" default below for universities
# that teach exclusively in English.
ENGLISH_TAUGHT_UNIVERSITY_SLUGS: set[str] = {"nazarbayev-university"}


async def _find_university(db: AsyncSession, record: dict) -> University | None:
    ovpo_code = record.get("ovpo_code")
    if ovpo_code:
        result = await db.execute(select(University).where(University.ovpo_code == ovpo_code))
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

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
    """Reproduces just enough of two earlier versions' naming schemes to find
    and delete rows seeded before this migration — not used for anything
    else. Covers raw group names, the old comma-joined synthesized name for
    generic group labels, and garbage specialty names now excluded outright."""
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
        directions_by_slug = {
            d.slug: d for d in (await db.execute(select(Direction))).scalars().all()
        }

        uni_inserted = uni_updated = uni_skipped = 0
        prog_inserted = prog_updated = prog_skipped = prog_deleted = 0
        unmapped: list[str] = []
        missing_direction_rows: set[str] = set()

        for record in ALL_UNIVERSITIES:
            existing_uni = await _find_university(db, record)

            if existing_uni is None:
                existing_uni = University(
                    name=record["name"],
                    slug=record["slug"],
                    ovpo_code=record.get("ovpo_code") or None,
                    short_name=record.get("short_name") or None,
                    aliases=record.get("aliases") or [],
                    location=record.get("location") or None,
                    country=record["country"],
                    city=record["city"],
                    website=record.get("website"),
                    ranking=None,
                    description=record.get("description") or "",
                )
                db.add(existing_uni)
                await db.flush()
                uni_inserted += 1
            else:
                changed = False
                if not existing_uni.slug:
                    existing_uni.slug = record["slug"]
                    changed = True
                if not existing_uni.ovpo_code and record.get("ovpo_code"):
                    existing_uni.ovpo_code = record["ovpo_code"]
                    changed = True
                if not existing_uni.description and record.get("description"):
                    existing_uni.description = record["description"]
                    changed = True
                if not existing_uni.short_name and record.get("short_name"):
                    existing_uni.short_name = record["short_name"]
                    changed = True
                if not existing_uni.aliases and record.get("aliases"):
                    existing_uni.aliases = record["aliases"]
                    changed = True
                if not existing_uni.location and record.get("location"):
                    existing_uni.location = record["location"]
                    changed = True
                if changed:
                    uni_updated += 1
                else:
                    uni_skipped += 1

            specialty_names = {
                name for group in record.get("specialties", []) for name in group["programs"]
            }
            # GARBAGE_SPECIALTIES must always be deleted even though they're
            # still literally present in specialty_names (they're skipped at
            # creation time below, but a prior run — before this exclusion
            # existed — may have already created a Program row for one).
            legacy_names = (_cleanup_legacy_group_names(record) - specialty_names) | (
                GARBAGE_SPECIALTIES & specialty_names
            )
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

            seen_specialty_names: set[str] = set()
            for group in record.get("specialties", []):
                group_name = group["group"]
                for specialty_name in group["programs"]:
                    if specialty_name in GARBAGE_SPECIALTIES:
                        continue
                    normalized_name = specialty_name.strip().lower()
                    if normalized_name in seen_specialty_names:
                        # Same specialty listed under two groups in the source data
                        # (a research artifact, not a real second program) — the
                        # (university_id, name_normalized) unique index would reject
                        # the second insert anyway, so skip it here up front.
                        continue
                    seen_specialty_names.add(normalized_name)

                    profession_slugs = SPECIALTY_TO_PROFESSIONS.get(specialty_name, [])
                    if not profession_slugs:
                        unmapped.append(f"{record['name']} / {group_name} / {specialty_name}")
                    missing_direction_rows.update(
                        slug for slug in profession_slugs if slug not in directions_by_slug
                    )
                    new_directions = [
                        directions_by_slug[slug]
                        for slug in profession_slugs
                        if slug in directions_by_slug
                    ]

                    prog_data = {
                        # KZ scrape default is "Казахский, Русский" for
                        # nearly every university — but a handful (currently
                        # just Nazarbayev University) teach exclusively in
                        # English, so the blanket default is wrong for them.
                        "language": "Английский" if record["slug"] in ENGLISH_TAUGHT_UNIVERSITY_SLUGS else "Казахский, Русский",
                        "cost_per_year": None,
                        # Deliberately left null, not group_name (e.g. "Школа
                        # медицины и педиатрии") — group_name is a
                        # faculty/specialty-group category label, not a real
                        # per-program description, and writing it here made
                        # ProgramListSection.tsx's frontend fallback to
                        # university.description (which only kicks in when
                        # program.description.length <= 40) skip long group
                        # labels that read as if they were real descriptions.
                        # See university-cards-ux-fix-plan.md §7 — the generic
                        # per-field diff below already nulls out any existing
                        # row still carrying the old stale group_name value on
                        # every rerun, no separate backfill needed.
                        "description": None,
                        "who_its_for": None,
                        "career_options": [],
                        "requirements": {"notes": admission_notes},
                        "deadlines": {},
                        "grants": [],
                    }

                    # Matched by name_normalized, not exact name — that's the
                    # actual (university_id, name_normalized) unique constraint
                    # this has to respect. An exact-name check misses e.g. an
                    # incoming plain "Биология" against an existing "Биология
                    # (бакалавр)" row, which normalize to the same value and
                    # would otherwise 500 on the unique-constraint violation.
                    result = await db.execute(
                        select(Program).where(
                            Program.university_id == existing_uni.id,
                            Program.name_normalized == specialty_name.strip().lower(),
                        )
                    )
                    existing_prog = result.scalar_one_or_none()

                    if existing_prog is None:
                        new_prog = Program(university_id=existing_uni.id, name=specialty_name, **prog_data)
                        new_prog.directions = new_directions
                        db.add(new_prog)
                        prog_inserted += 1
                    else:
                        changed = False
                        # `requirements` is handled separately from the generic
                        # per-field diff below: this scrape only ever knows
                        # about `notes`, but later pipeline steps (grant/ENT
                        # backfills) add exams/min_ent_threshold/
                        # admission_scores_2026/needs_* into the SAME dict.
                        # Comparing/overwriting the whole dict against a
                        # source that only has `notes` made a rerun of this
                        # script wipe all of that enrichment on every existing
                        # row (found via a live full-reseed test — every KZ
                        # program's requirements collapsed back down to just
                        # {"notes": [...]}). Merge instead: only touch the
                        # `notes` key, leave every other key whatever it is.
                        if existing_prog.requirements.get("notes") != admission_notes:
                            existing_prog.requirements = {**existing_prog.requirements, "notes": admission_notes}
                            changed = True
                        for field, value in prog_data.items():
                            if field == "requirements":
                                continue
                            if getattr(existing_prog, field) != value:
                                setattr(existing_prog, field, value)
                                changed = True
                        if {d.slug for d in existing_prog.directions} != set(profession_slugs):
                            existing_prog.directions = new_directions
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
        f"stale/garbage rows deleted: {prog_deleted}."
    )
    if unmapped:
        print(
            f"\n{len(unmapped)} specialty(ies) have no profession mapping — "
            f"review scripts/specialty_profession_map.py:"
        )
        for name in unmapped:
            print(f"  - {name}")
    if missing_direction_rows:
        print(
            f"\n{len(missing_direction_rows)} profession slug(s) mapped in "
            f"specialty_profession_map.py have no matching Direction row in "
            f"the DB, so they were skipped instead of linked:"
        )
        for slug in sorted(missing_direction_rows):
            print(f"  - {slug}")


if __name__ == "__main__":
    asyncio.run(main())
