"""
Idempotent script: backfills updated_at and source_url columns for programs
that were modified by scripts/apply_grant_admission_data_2026.py.

Key rules:
- Reads scripts/data/db_updates_2026.json
- Resolves each program by university slug + program name (via
  scripts/entity_resolver.py), NOT by the dict key — that key is a snapshot
  of Program.id (a per-database random uuid4()) taken from whatever DB the
  file was generated against, so it resolves to nothing on any other
  database (see docs/content-pipeline-id-resolution-audit.md). Every value
  in the file already carries `slug` + `name`, which do resolve.
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

from app.database import async_session
from scripts.entity_resolver import resolve_program, resolve_university

DATA_PATH = os.path.join(_ROOT, "scripts", "data", "db_updates_2026.json")


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    with open(DATA_PATH, encoding="utf-8") as f:
        updates: dict[str, dict] = json.load(f)

    async with async_session() as db:
        updated = 0
        unchanged = 0
        skipped_no_key = 0
        missing: list[str] = []

        for program_id, payload in updates.items():
            slug = payload.get("slug")
            name = payload.get("name")
            if not slug or not name:
                skipped_no_key += 1
                continue

            university, _ = await resolve_university(db, slug=slug)
            program = await resolve_program(db, university=university, name=name) if university else None
            if program is None:
                # program_id kept in the message only as a breadcrumb back to
                # the source file — it is not what we matched on.
                missing.append(f"{slug} / {name} (snapshot id {program_id})")
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
                    print(f"[would backfill] {slug} / {name} -> {source_url}")
                else:
                    program.updated_at = datetime.now(timezone.utc)
                    program.source_url = source_url
            else:
                unchanged += 1

        if not dry_run:
            await db.commit()

        print(
            f"\n{'DRY RUN — ' if dry_run else ''}programs updated: {updated}, "
            f"unchanged: {unchanged}, missing: {len(missing)}, skipped (no slug/name): {skipped_no_key}"
        )
        if missing:
            print("Not found on this DB (resolved by slug + name):")
            for m in missing:
                print(f"  - {m}")


if __name__ == "__main__":
    asyncio.run(main())
