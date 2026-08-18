"""
Idempotent update: writes 2026-2027 grant admission data into Program.requirements
for the 517 programs (across 39 universities whose ОВПО code was identified in the
official grants PDF + MES RK ENT-threshold reference) resolved during this session.

Two disjoint data kinds, merged into the existing `requirements` dict without
touching the pre-existing `notes` key:
  - admission_scores_2026: real minimum score that won a grant in the 2026-2027
    general-competition admission (from the official PDF, general + MOH sections,
    full-time full-length study, "Общий конкурс" quota only). Present only for
    programs where this year's PDF actually had grant recipients for that
    (specialty group, university) pair.
  - exams + min_ent_threshold: the official MES RK ENT subject pair and minimum
    admission threshold for programs where no 2026-2027 grant-competition data
    exists in the source document (so this is the closest verifiable fact
    available: what's needed to even be eligible, not what won a grant this year).

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/apply_grant_admission_data_2026.py [--dry-run]
"""
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program

DATA_PATH = "scripts/data/db_updates_2026.json"


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    with open(DATA_PATH, encoding="utf-8") as f:
        updates: dict[str, dict] = json.load(f)

    async with async_session() as db:
        updated = 0
        unchanged = 0
        missing: list[str] = []

        for program_id, payload in updates.items():
            result = await db.execute(select(Program).where(Program.id == program_id))
            program = result.scalar_one_or_none()
            if program is None:
                missing.append(f"{payload['slug']} / {payload['name']} ({program_id})")
                continue

            requirements = dict(program.requirements or {})
            changed = False

            if "admission_scores_2026" in payload:
                if requirements.get("admission_scores_2026") != payload["admission_scores_2026"]:
                    requirements["admission_scores_2026"] = payload["admission_scores_2026"]
                    changed = True

            if "exams" in payload:
                if requirements.get("exams") != payload["exams"]:
                    requirements["exams"] = payload["exams"]
                    changed = True
                if requirements.get("min_ent_threshold") != payload["min_ent_threshold"]:
                    requirements["min_ent_threshold"] = payload["min_ent_threshold"]
                    changed = True

            if changed:
                updated += 1
                if dry_run:
                    print(f"[would update] {payload['slug']} / {payload['name']}")
                else:
                    program.requirements = requirements
            else:
                unchanged += 1

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}programs updated: {updated}, unchanged: {unchanged}, missing: {len(missing)}")
        if missing:
            print("Missing program IDs (not found in DB):")
            for m in missing:
                print(f"  - {m}")


if __name__ == "__main__":
    asyncio.run(main())
