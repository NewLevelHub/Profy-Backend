"""
Seed script: populate motivation_pairs from motivation_pair_bank.py.
Run inside Docker: docker-compose exec api python scripts/seed_motivation_pairs.py

Idempotent, self-healing: upserts by pair_index, deletes any DB row whose
pair_index is no longer present in PAIRS — same pattern as the other seed
scripts.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.models.motivation import MotivationCategory
from app.models.motivation_pair import MotivationPair
from app.database import async_session
from scripts.motivation_pair_bank import PAIRS


async def main() -> None:
    async with async_session() as db:
        live_keys = {p["pair_index"] for p in PAIRS}

        existing_result = await db.execute(select(MotivationPair))
        existing_by_key = {p.pair_index: p for p in existing_result.scalars().all()}

        inserted = 0
        updated = 0
        skipped = 0
        deleted = 0

        for data in PAIRS:
            key = data["pair_index"]
            existing = existing_by_key.get(key)
            category_a = MotivationCategory(data["category_a"])
            category_b = MotivationCategory(data["category_b"])

            if existing is not None:
                changed = False
                if existing.category_a != category_a:
                    existing.category_a = category_a
                    changed = True
                if existing.category_b != category_b:
                    existing.category_b = category_b
                    changed = True
                if existing.text_a != data["text_a"]:
                    existing.text_a = data["text_a"]
                    changed = True
                if existing.text_b != data["text_b"]:
                    existing.text_b = data["text_b"]
                    changed = True
                if changed:
                    updated += 1
                else:
                    skipped += 1
                continue

            db.add(
                MotivationPair(
                    pair_index=data["pair_index"],
                    category_a=category_a,
                    category_b=category_b,
                    text_a=data["text_a"],
                    text_b=data["text_b"],
                )
            )
            inserted += 1

        for key, pair in existing_by_key.items():
            if key not in live_keys:
                await db.delete(pair)
                deleted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(f"Total pairs in bank: {len(PAIRS)}")


if __name__ == "__main__":
    asyncio.run(main())
