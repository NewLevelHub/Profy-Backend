"""
Seeds University + Program rows from scripts/data/universities_92_professions.py
(extracted from "Университеты для 92 профессий.txt"): 13 clusters, each with
1 Kazakhstani regional university + 3-4 world universities, each linked to
every profession/Direction in that cluster via a dedicated Program row.

Idempotent:
  - University upserted by slug — an existing row is left untouched (a
    university recurring across clusters keeps whichever cluster's write-up
    it was first created with; the per-cluster text always survives on
    Program.description instead).
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
from scripts.data.universities_92_professions import CLUSTERS

RANK_RE = re.compile(r"#(\d+)")


def parse_ranking(label: str) -> int | None:
    m = RANK_RE.search(label)
    return int(m.group(1)) if m else None


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        directions_by_slug = {d.slug: d for d in (await db.execute(select(Direction))).scalars().all()}
        universities_by_slug = {u.slug: u for u in (await db.execute(select(University))).scalars().all()}

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
                university = universities_by_slug.get(slug)

                if university is None:
                    universities_created += 1
                    if dry_run:
                        print(f"[would create university] {slug} — {uni_data['name']}")
                    else:
                        university = University(
                            name=uni_data["name"],
                            slug=slug,
                            short_name=uni_data.get("short_name"),
                            aliases=[],
                            location=None,
                            country=uni_data["country"],
                            city=uni_data["city"],
                            website=None,
                            ranking=parse_ranking(uni_data["ranking_label"]),
                            ranking_label=uni_data["ranking_label"],
                            description=uni_data["description"],
                        )
                        db.add(university)
                        await db.flush()
                        universities_by_slug[slug] = university
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
                    program_name = direction.name
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
