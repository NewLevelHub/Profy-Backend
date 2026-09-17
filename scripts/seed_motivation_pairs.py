"""
Seed script: populate motivation_pairs from motivation_pair_bank.py.
Run inside Docker: docker-compose exec api python scripts/seed_motivation_pairs.py

Idempotent, self-healing: upserts by `pair_index`, deletes any DB row whose
`pair_index` is no longer present in PAIRS. Admin-overridden fields/rows are
preserved (admin_lock.sync_fields / has_overrides).

Localized (single-row redesign, docs/i18n-contract.md §8): one logical pair =
one row, `text_a`/`text_b` stored whole as their bank `{locale: str}` maps —
`category_a`/`category_b` (the a=positive-pole / b=negative-pole convention)
are physically shared, not just conventionally identical.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.models.motivation import MotivationCategory
from app.models.motivation_pair import LOCALIZED_FIELDS, MotivationPair
from app.database import async_session
from app.services.admin_lock import has_overrides, sync_fields
from scripts.motivation_pair_bank import PAIRS


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        live_keys = {p["pair_index"] for p in PAIRS}
        existing_result = await db.execute(select(MotivationPair))
        existing_by_key = {p.pair_index: p for p in existing_result.scalars().all()}

        for data in PAIRS:
            existing = existing_by_key.get(data["pair_index"])
            if existing is not None:
                changed = sync_fields(
                    existing,
                    {
                        "category_a": MotivationCategory(data["category_a"]),
                        "category_b": MotivationCategory(data["category_b"]),
                        "text_a": data["text_a"],
                        "text_b": data["text_b"],
                    },
                    localized_fields=LOCALIZED_FIELDS,
                )
                updated += changed
                skipped += not changed
                continue

            db.add(
                MotivationPair(
                    pair_index=data["pair_index"],
                    category_a=MotivationCategory(data["category_a"]),
                    category_b=MotivationCategory(data["category_b"]),
                    text_a=data["text_a"],
                    text_b=data["text_b"],
                )
            )
            inserted += 1

        for key, pair in existing_by_key.items():
            if key not in live_keys and not has_overrides(pair):
                await db.delete(pair)
                deleted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(f"Bank: {len(PAIRS)} logical pairs")


if __name__ == "__main__":
    asyncio.run(main())
