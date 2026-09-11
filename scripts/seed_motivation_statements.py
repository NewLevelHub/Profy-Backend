"""
Seed script: populate motivation_statements from motivation_statement_bank.py.
Run inside Docker: docker-compose exec api python scripts/seed_motivation_statements.py

Idempotent, self-healing: upserts by `(triplet_index, order, locale)`, deletes
any DB row whose `(triplet_index, order, locale)` is no longer present in
STATEMENTS *for that locale* — same pattern as seed_riasec_questions.py.
Admin-overridden fields/rows are preserved (admin_lock.sync_fields / has_overrides).

Localized (KZ-301/KZ-305): each statement carries `text` / `text_junior` as
`{locale: str}`; `LOCALES` lists the bank's locales. One logical statement =
one row per locale, keyed `(triplet_index, order, locale)`, identical
`category` across locales.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.motivation import MotivationCategory, MotivationStatement
from app.services.admin_lock import has_overrides, sync_fields
from scripts.motivation_statement_bank import LOCALES, STATEMENTS


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        for locale in LOCALES:
            live = [s for s in STATEMENTS if locale in s["text"]]
            live_keys = {(s["triplet_index"], s["order"]) for s in live}

            existing_result = await db.execute(
                select(MotivationStatement).where(MotivationStatement.locale == locale)
            )
            existing_by_key = {
                (q.triplet_index, q.order): q for q in existing_result.scalars().all()
            }

            for data in live:
                category = MotivationCategory(data["category"])
                text = data["text"][locale]
                text_junior = data["text_junior"][locale]

                existing = existing_by_key.get((data["triplet_index"], data["order"]))
                if existing is not None:
                    changed = sync_fields(existing, {
                        "category": category,
                        "text": text,
                        "text_junior": text_junior,
                    })
                    updated += changed
                    skipped += not changed
                    continue

                db.add(
                    MotivationStatement(
                        triplet_index=data["triplet_index"],
                        order=data["order"],
                        category=category,
                        text=text,
                        text_junior=text_junior,
                        locale=locale,
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
        print(f"Bank: {len(STATEMENTS)} logical statements x locales {LOCALES}")


if __name__ == "__main__":
    asyncio.run(main())
