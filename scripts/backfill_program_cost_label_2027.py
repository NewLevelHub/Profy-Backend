"""
Fixes Program rows created by an earlier version of
seed_92_professions_universities.py, which smashed cost and admission-
requirements text together into a single Program.requirements["notes"]
string (itself stored as a bare string, not list[str] — a second bug already
patched). Neither the cost nor the notes ever reached a field the UI actually
reads: cost_per_year stayed None (correctly — these are ranges/mixed
currencies, see scripts/data/universities_92_professions.py's docstring), so
program cards showed "Стоимость не указана" even though a real cost range was
sitting unread inside the notes text.

Walks CLUSTERS the same way the seed script does (university slug -> that
cluster's direction_objs) and, for each already-existing Program matched by
(university_id, name == direction.name), sets:
  - cost_label = uni_data["cost_text"]        (free-text fallback next to cost_per_year)
  - requirements["notes"] = [uni_data["requirements_text"]]   (cost stripped out)

Also keeps a defensive fallback for any other Program (outside this data
source) whose notes is still a bare string — wraps it in a list, same fix as
the now-superseded backfill_notes_list_2027.py.

Idempotent: recomputes the same target values every run, safe to re-run.

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/backfill_program_cost_label_2027.py [--dry-run]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.direction import Direction
from app.models.program import Program
from app.models.university import University
from scripts.data.universities_92_professions import CLUSTERS


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        directions_by_slug = {d.slug: d for d in (await db.execute(select(Direction))).scalars().all()}
        universities_by_slug = {u.slug: u for u in (await db.execute(select(University))).scalars().all()}
        programs_by_key = {
            (p.university_id, p.name): p
            for p in (await db.execute(select(Program))).scalars().all()
        }

        fixed = 0
        unchanged = 0
        missing: list[str] = []

        touched_ids: set = set()

        for cluster in CLUSTERS:
            direction_objs = [
                directions_by_slug[slug] for slug in cluster["directions"] if slug in directions_by_slug
            ]

            for uni_data in cluster["universities"]:
                slug = uni_data["slug"]
                university = universities_by_slug.get(slug)
                if university is None:
                    missing.append(slug)
                    continue

                cost_label = uni_data["cost_text"]
                notes = [uni_data["requirements_text"]]

                for direction in direction_objs:
                    program = programs_by_key.get((university.id, direction.name))
                    if program is None:
                        continue
                    touched_ids.add(program.id)

                    changed = (
                        program.cost_label != cost_label
                        or program.requirements.get("notes") != notes
                    )
                    if not changed:
                        unchanged += 1
                        continue

                    fixed += 1
                    if dry_run:
                        print(f"[would fix] {slug} / {direction.name} -> cost_label={cost_label!r}")
                    else:
                        program.cost_label = cost_label
                        program.requirements = {**program.requirements, "notes": notes}

        # Defensive net: any program outside this data source whose notes is
        # still a bare string (same class of bug, different origin).
        for program in programs_by_key.values():
            if program.id in touched_ids:
                continue
            notes = program.requirements.get("notes")
            if not isinstance(notes, str):
                continue
            fixed += 1
            if dry_run:
                print(f"[would fix] {program.id} ({program.name!r}) -> wrap {len(notes)}-char string in a list")
            else:
                program.requirements = {**program.requirements, "notes": [notes]}

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}programs fixed: {fixed}, unchanged: {unchanged}, missing universities: {len(missing)}")
        if missing:
            print("Missing slugs (not found in DB):")
            for m in missing:
                print(f"  - {m}")


if __name__ == "__main__":
    asyncio.run(main())
