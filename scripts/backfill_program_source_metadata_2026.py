"""
Idempotent script: backfills updated_at and source_url columns for programs
that were modified by scripts/apply_grant_admission_data_2026.py.

Key rules:
- Reads scripts/data/db_updates_2026.json
- Skips programs if program.updated_at is not None (does not overwrite real admin updates)
- Sets source_url and updated_at based on payload keys
- Supports --dry-run
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

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
                missing.append(f"{payload.get('slug')} / {payload.get('name')} ({program_id})")
                continue

            # Skip if already updated/verified by an admin
            if program.updated_at is not None:
                unchanged += 1
                continue

            # Determine the source URL
            source_url = None
            if "admission_scores_2026" in payload:
                source_url = "Официальный список грантников 2026-2027 (МОН РК, общий конкурс)"
            elif "exams" in payload or "min_ent_threshold" in payload:
                source_url = "Норматив МОН РК: профильная пара ЕНТ и пороговый балл допуска, 2026"

            if source_url:
                updated += 1
                if dry_run:
                    print(f"[would backfill] {payload.get('slug')} / {payload.get('name')} -> {source_url}")
                else:
                    program.updated_at = datetime.now(timezone.utc)
                    program.source_url = source_url
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
