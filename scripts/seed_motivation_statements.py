"""
Seed script: populate motivation_statements from motivation_statement_bank.py.
Run inside Docker: docker-compose exec api python scripts/seed_motivation_statements.py

Idempotent, self-healing: upserts by `(triplet_index, order)`, deletes any DB
row whose key is no longer present in STATEMENTS. Admin-overridden
fields/rows are preserved (admin_lock.sync_fields / has_overrides).

Localized (single-row redesign, docs/i18n-contract.md §8): one logical
statement = one row, `text`/`text_junior` stored whole as their bank
`{locale: str}` maps.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.motivation import LOCALIZED_FIELDS, MotivationCategory, MotivationStatement
from app.services.admin_lock import has_overrides, sync_fields
from scripts.motivation_statement_bank import STATEMENTS


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        live_keys = {(s["triplet_index"], s["order"]) for s in STATEMENTS}
        existing_result = await db.execute(select(MotivationStatement))
        existing_by_key = {
            (q.triplet_index, q.order): q for q in existing_result.scalars().all()
        }

        for data in STATEMENTS:
            key = (data["triplet_index"], data["order"])
            existing = existing_by_key.get(key)
            if existing is not None:
                changed = sync_fields(
                    existing,
                    {
                        "category": MotivationCategory(data["category"]),
                        "text": data["text"],
                        "text_junior": data["text_junior"],
                    },
                    localized_fields=LOCALIZED_FIELDS,
                )
                updated += changed
                skipped += not changed
                continue

            db.add(
                MotivationStatement(
                    triplet_index=data["triplet_index"],
                    order=data["order"],
                    category=MotivationCategory(data["category"]),
                    text=data["text"],
                    text_junior=data["text_junior"],
                )
            )
            inserted += 1

        for key, statement in existing_by_key.items():
            if key not in live_keys and not has_overrides(statement):
                await db.delete(statement)
                deleted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(f"Bank: {len(STATEMENTS)} logical statements")


if __name__ == "__main__":
    asyncio.run(main())
