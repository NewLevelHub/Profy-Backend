"""Applies the human-reviewed output of generate_program_requirements_content.py
to the `programs` table. Separate from generation on purpose — the user
reviews program_requirements_review_2027.json before this script runs;
generation itself never touches the DB.

Only ever writes requirements["exams"/"needs_portfolio"/"needs_essay"/
"needs_recommendations"/"needs_interview"] and deadlines["application_close"]
— never touches requirements["notes"]/cost_label (owned by
seed_92_professions_universities.py / backfill_program_cost_label_2027.py).
Booleans are only written when not null in the review file — a missing key
means "no data" to university_requirements.py, same as an explicit None ever
would, so there's no need to write `null` explicitly.

Idempotent: re-running with the same reviewed file re-applies the same
values. Matched by program_id (from the review file's program_ids list), not
by slug — a group can map to many programs.

Run inside Docker: docker compose exec api python scripts/apply_program_requirements_content_2027.py [--dry-run]
"""
import asyncio
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.services.admin_lock import is_locked

REVIEW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "program_requirements_review_2027.json")

_BOOL_KEYS = ("needs_portfolio", "needs_essay", "needs_recommendations", "needs_interview")


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    with open(REVIEW_PATH, encoding="utf-8") as f:
        groups = json.load(f)

    async with async_session() as db:
        result = await db.execute(select(Program))
        programs_by_id = {p.id: p for p in result.scalars().all()}

        updated = 0
        missing: list[str] = []

        for group in groups:
            for pid_str in group["program_ids"]:
                program = programs_by_id.get(uuid.UUID(pid_str))
                if program is None:
                    missing.append(pid_str)
                    continue

                requirements_locked = is_locked(program, "requirements")
                deadlines_locked = is_locked(program, "deadlines")
                if requirements_locked:
                    print(f"Skipping requirements for {program.name} ({pid_str}) — admin-locked")
                if deadlines_locked:
                    print(f"Skipping deadlines for {program.name} ({pid_str}) — admin-locked")
                if requirements_locked and deadlines_locked:
                    continue

                new_requirements = dict(program.requirements)
                if group.get("exams"):
                    new_requirements["exams"] = group["exams"]
                for key in _BOOL_KEYS:
                    if group.get(key) is not None:
                        new_requirements[key] = group[key]

                new_deadlines = dict(program.deadlines)
                if group.get("application_deadline"):
                    new_deadlines["application_close"] = group["application_deadline"]

                if dry_run:
                    print(f"[would update] {program.name} ({pid_str}) -> exams={group.get('exams')}")
                else:
                    if not requirements_locked:
                        program.requirements = new_requirements
                    if not deadlines_locked:
                        program.deadlines = new_deadlines
                updated += 1

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}programs updated: {updated}, missing: {len(missing)}")
        if missing:
            print(f"Program ids in review file but not found in DB (skipped): {missing}")


if __name__ == "__main__":
    asyncio.run(main())
