"""
Seed script: populate motivation_pairs from motivation_pair_bank.py.
Run inside Docker: docker-compose exec api python scripts/seed_motivation_pairs.py

Idempotent, self-healing: upserts by `(pair_index, locale)`, deletes any DB row
whose `(pair_index, locale)` is no longer present in PAIRS *for that locale* —
same pattern as the other seed scripts.

Localized (KZ-301/KZ-305): each pair carries `text_a` / `text_b` as
`{locale: str}`; `LOCALES` lists the bank's locales. One logical pair = one row
per locale, keyed `(pair_index, locale)`, identical `category_a` / `category_b`
across locales (the a=positive-pole / b=negative-pole convention is preserved
in the translation, so motivation_pair_service scoring is unchanged).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.models.motivation import MotivationCategory
from app.models.motivation_pair import MotivationPair
from app.database import async_session
from scripts.motivation_pair_bank import LOCALES, PAIRS


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        for locale in LOCALES:
            live = [p for p in PAIRS if locale in p["text_a"]]
            live_keys = {p["pair_index"] for p in live}

            existing_result = await db.execute(
                select(MotivationPair).where(MotivationPair.locale == locale)
            )
            existing_by_key = {p.pair_index: p for p in existing_result.scalars().all()}

            for data in live:
                category_a = MotivationCategory(data["category_a"])
                category_b = MotivationCategory(data["category_b"])
                text_a = data["text_a"][locale]
                text_b = data["text_b"][locale]

                existing = existing_by_key.get(data["pair_index"])
                if existing is not None:
                    changed = False
                    if existing.category_a != category_a:
                        existing.category_a = category_a
                        changed = True
                    if existing.category_b != category_b:
                        existing.category_b = category_b
                        changed = True
                    if existing.text_a != text_a:
                        existing.text_a = text_a
                        changed = True
                    if existing.text_b != text_b:
                        existing.text_b = text_b
                        changed = True
                    updated += changed
                    skipped += not changed
                    continue

                db.add(
                    MotivationPair(
                        pair_index=data["pair_index"],
                        category_a=category_a,
                        category_b=category_b,
                        text_a=text_a,
                        text_b=text_b,
                        locale=locale,
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
        print(f"Bank: {len(PAIRS)} logical pairs x locales {LOCALES}")


if __name__ == "__main__":
    asyncio.run(main())
