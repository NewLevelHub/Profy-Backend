"""
Idempotent update: writes UNIRANKS® 2027 Kazakhstan ranking (national position
+ world rank) into University.uniranks_kz_rank / uniranks_world_rank for the
universities matched by slug against https://www.uniranks.com/ranking/ru/казахстан.

Entries flagged "best_guess": true in the data file matched by institution
identity/theme rather than an exact name string (e.g. renamed institutions) —
review scripts/data/uniranks_kz_2027.json before trusting those rows blindly.

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/apply_uniranks_kz_2027.py [--dry-run]
"""
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.university import University

DATA_PATH = os.path.join(_ROOT, "scripts", "data", "uniranks_kz_2027.json")


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    with open(DATA_PATH, encoding="utf-8") as f:
        updates: dict[str, dict] = json.load(f)

    async with async_session() as db:
        updated = 0
        unchanged = 0
        missing: list[str] = []

        for slug, payload in updates.items():
            result = await db.execute(select(University).where(University.slug == slug))
            university = result.scalar_one_or_none()
            if university is None:
                missing.append(f"{slug} / {payload['name']}")
                continue

            changed = (
                university.uniranks_kz_rank != payload["kz_rank"]
                or university.uniranks_world_rank != payload["world_rank"]
            )

            if changed:
                updated += 1
                tag = " [best-guess match]" if payload.get("best_guess") else ""
                if dry_run:
                    print(f"[would update] {slug} -> kz_rank={payload['kz_rank']}, world_rank={payload['world_rank']}{tag}")
                else:
                    university.uniranks_kz_rank = payload["kz_rank"]
                    university.uniranks_world_rank = payload["world_rank"]
            else:
                unchanged += 1

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}universities updated: {updated}, unchanged: {unchanged}, missing: {len(missing)}")
        if missing:
            print("Missing slugs (not found in DB):")
            for m in missing:
                print(f"  - {m}")


if __name__ == "__main__":
    asyncio.run(main())
