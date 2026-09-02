"""
Seed script: populate motivation_statements from motivation_statement_bank.py.
Run inside Docker: docker-compose exec api python scripts/seed_motivation_statements.py

Idempotent, self-healing: upserts by (triplet_index, order), deletes any DB
row whose (triplet_index, order) pair is no longer present in STATEMENTS —
same pattern as seed_riasec_questions.py.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.motivation import MotivationCategory, MotivationStatement
from app.services.admin_lock import effective_value, has_overrides
from scripts.motivation_statement_bank import STATEMENTS


async def main() -> None:
    async with async_session() as db:
        live_keys = {(s["triplet_index"], s["order"]) for s in STATEMENTS}

        existing_result = await db.execute(select(MotivationStatement))
        existing_by_key = {
            (q.triplet_index, q.order): q for q in existing_result.scalars().all()
        }

        inserted = 0
        updated = 0
        skipped = 0
        deleted = 0

        for data in STATEMENTS:
            key = (data["triplet_index"], data["order"])
            existing = existing_by_key.get(key)
            category = MotivationCategory(data["category"])

            if existing is not None:
                changed = False
                target = effective_value(existing, "category", category)
                if existing.category != target:
                    existing.category = target
                    changed = True
                target = effective_value(existing, "text", data["text"])
                if existing.text != target:
                    existing.text = target
                    changed = True
                target = effective_value(existing, "text_junior", data.get("text_junior"))
                if existing.text_junior != target:
                    existing.text_junior = target
                    changed = True
                if changed:
                    updated += 1
                else:
                    skipped += 1
                continue

            db.add(
                MotivationStatement(
                    triplet_index=data["triplet_index"],
                    order=data["order"],
                    category=category,
                    text=data["text"],
                    text_junior=data.get("text_junior"),
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
        print(f"Total statements in bank: {len(STATEMENTS)}")


if __name__ == "__main__":
    asyncio.run(main())
