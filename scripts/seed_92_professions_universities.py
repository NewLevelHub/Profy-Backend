"""
Seeds University + Program rows from scripts/data/universities_92_professions.py
(extracted from "Университеты для 92 профессий.txt"): 13 clusters, each with
1 Kazakhstani regional university + 3-4 world universities, each linked to
every profession/Direction in that cluster via a dedicated Program row.

Idempotent:
  - University upserted by ror_id when the data entry has one (canonical key,
    see docs/university-module-fix-plan.md B1 — look one up with
    scripts/find_ror_id.py before adding a new foreign university), falling
    back to slug otherwise. An existing row is left untouched (a university
    recurring across clusters keeps whichever cluster's write-up it was first
    created with; the per-cluster text always survives on Program.description
    instead).
  - Program matched by (university_id, name) — reruns don't duplicate.

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/seed_92_professions_universities.py [--dry-run]
"""
import asyncio
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.direction import Direction
from app.models.program import Program
from app.models.university import University
from scripts.data.direction_program_names import DIRECTION_SLUG_TO_PROGRAM_NAME
from scripts.data.universities_92_professions import CLUSTERS

# A ranking_label routinely packs a global rank together with a
# subject/national/regional one in the same string, comma- or
# semicolon-separated (e.g. "#4 инженерных школ США (US News 2026), #32
# среди национальных университетов США" — both numbers are real, neither is
# a world rank). `ranking` feeds cross-university sorting on the frontend
# (university-cards-ux-fix-plan.md §1), so it must only ever hold a number
# that's actually comparable across every university — i.e. an explicit
# global/world-scope rank. A subject-specific or national number must never
# leak in just because it happened to be the first digit in the string, or
# sorting silently compares incomparable scales (this is exactly what
# produced Georgia Tech's #4 US-News-engineering-schools ranking outranking
# ETH Zurich's #7 QS World in the unified list).
#
# QS only, deliberately — product decision: the unified cross-university
# rank must come from one single system, not "whichever global-sounding
# number happens to be in the label" (QS and THE use different
# methodologies and aren't on the same scale either, even though both are
# "world" rankings). Only 2 of 148 labels rely on THE with no QS number at
# all (ENAC Toulouse, Semmelweis University) — both correctly fall back to
# "no unified rank" (sorts last) rather than mixing in a THE number.
_WORLD_SCOPE_RE = re.compile(
    r"QS\s+World|World\s+University\s+Rankings",
    re.IGNORECASE,
)
# "QS World" also shows up in QS's *subject* rankings (e.g. "QS World -
# Petroleum Engineering", "QS World Medicine 2025", "QS World University
# Rankings by Subject — Law") — these are just as real as the overall list,
# but they're a different, non-comparable scale from a different university's
# overall QS World position, so a clause naming a specific subject/field must
# not be accepted as the unified rank either, even though it also says
# "World". Only a bare/overall QS World Rankings clause counts.
_SUBJECT_QUALIFIED_WORLD_RE = re.compile(
    r"by\s+Subject|Subject\s*[:—-]|"
    r"World\s*[-–—]\s*\w|"
    r"World\s+(?:Medicine|Law\s+Rank|Ranking\s+Business)|"
    r"по\s+направлению|"
    r"в\s+(?:сельскохозяйственных|агрономии)",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"(\d+)")


def parse_ranking(label: str) -> int | None:
    # Only trust a clause that explicitly claims global/world scope *and*
    # isn't itself qualified down to one subject; take the first number
    # *within that clause*. Any other clause (subject-specific, national,
    # regional) is ignored entirely rather than falling back to "first
    # number anywhere in the label" — no unified rank is safer than a wrong
    # one (see docstring above and university-cards-ux-fix-plan.md §1).
    for clause in re.split(r"[,;]", label):
        if _WORLD_SCOPE_RE.search(clause) and not _SUBJECT_QUALIFIED_WORLD_RE.search(clause):
            m = _NUMBER_RE.search(clause)
            if m:
                return int(m.group(1))
    return None


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        directions_by_slug = {d.slug: d for d in (await db.execute(select(Direction))).scalars().all()}
        all_universities = (await db.execute(select(University))).scalars().all()
        universities_by_slug = {u.slug: u for u in all_universities}
        # Canonical dedup key for foreign universities (docs/university-module-fix-plan.md B1) —
        # checked ahead of slug so a ror_id match wins even if the data file's slug
        # for the same institution ever drifts from what's already in the DB.
        universities_by_ror_id = {u.ror_id: u for u in all_universities if u.ror_id}

        universities_created = 0
        universities_existing = 0
        programs_created = 0
        programs_existing = 0
        missing_directions: set[str] = set()

        for cluster in CLUSTERS:
            direction_objs = []
            for slug in cluster["directions"]:
                d = directions_by_slug.get(slug)
                if d is None:
                    missing_directions.add(slug)
                else:
                    direction_objs.append(d)

            for uni_data in cluster["universities"]:
                slug = uni_data["slug"]
                ror_id = uni_data.get("ror_id")
                university = (universities_by_ror_id.get(ror_id) if ror_id else None) or universities_by_slug.get(slug)

                if university is None:
                    universities_created += 1
                    if dry_run:
                        print(f"[would create university] {slug} — {uni_data['name']}")
                    else:
                        university = University(
                            name=uni_data["name"],
                            slug=slug,
                            ror_id=ror_id,
                            short_name=uni_data.get("short_name"),
                            aliases=[],
                            location=None,
                            country=uni_data["country"],
                            city=uni_data["city"],
                            website=uni_data.get("website"),
                            ranking=parse_ranking(uni_data["ranking_label"]),
                            ranking_label=uni_data["ranking_label"],
                            description=uni_data["description"],
                        )
                        db.add(university)
                        await db.flush()
                        universities_by_slug[slug] = university
                        if ror_id:
                            universities_by_ror_id[ror_id] = university
                else:
                    universities_existing += 1

                if university is None:
                    # dry-run: nothing to attach programs to yet
                    continue

                # cost_text goes on Program.cost_label (free-text fallback next to
                # cost_per_year, which stays None — ranges/mixed currencies don't fit
                # a single Decimal). requirements["notes"] holds only the admission
                # requirements prose, not the cost — university_requirements.py does
                # `list(requirements.get("notes") or [])`, and `list()` on a bare
                # string explodes it into one entry per character, not per note, so
                # this must already be a list.
                cost_label = uni_data["cost_text"]
                notes = [uni_data["requirements_text"]]
                grants = [{"name": uni_data["grants_text"]}]

                for direction in direction_objs:
                    # A foreign university doesn't offer a program literally
                    # titled after the Russian profession name (e.g.
                    # "Инженер-механик") — use the equivalent internationally
                    # recognized academic field name instead. Kazakhstani
                    # universities in these clusters keep the profession name
                    # (their real specialty titles are in Russian, not this
                    # English map).
                    program_name = (
                        DIRECTION_SLUG_TO_PROGRAM_NAME.get(direction.slug, direction.name)
                        if uni_data["country"] != "Казахстан"
                        else direction.name
                    )
                    existing = await db.execute(
                        select(Program).where(
                            Program.university_id == university.id,
                            Program.name == program_name,
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        programs_existing += 1
                        continue

                    programs_created += 1
                    if dry_run:
                        print(f"[would create program] {slug} / {program_name}")
                    else:
                        program = Program(
                            university_id=university.id,
                            name=program_name,
                            language=uni_data["language"],
                            cost_per_year=None,
                            cost_label=cost_label,
                            description=uni_data["description"],
                            who_its_for=None,
                            career_options=[],
                            requirements={"notes": notes},
                            deadlines={},
                            grants=grants,
                            source_url=None,
                        )
                        program.directions = [direction]
                        db.add(program)

        if not dry_run:
            await db.commit()

        print(
            f"\n{'DRY RUN — ' if dry_run else ''}"
            f"universities created: {universities_created}, existing: {universities_existing}; "
            f"programs created: {programs_created}, existing: {programs_existing}"
        )
        if missing_directions:
            print("Missing direction slugs (not found in DB):")
            for m in sorted(missing_directions):
                print(f"  - {m}")


if __name__ == "__main__":
    asyncio.run(main())
