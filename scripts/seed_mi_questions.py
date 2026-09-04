"""
Seed script: populate the questions table (MI rows) from mi_question_bank.py.
Run inside Docker, AFTER seed_riasec_questions.py and seed_bigfive_questions.py
(order continues from their combined bank length):
docker-compose exec api python scripts/seed_mi_questions.py

Idempotent, self-healing: upserts by `(order, locale)`, deletes any mi DB row
whose `(order, locale)` is no longer present in QUESTIONS *for that locale* —
same pattern as seed_riasec_questions.py/seed_bigfive_questions.py. Only touches
instrument='mi'. Admin-overridden fields/rows are preserved
(admin_lock.sync_fields / has_overrides).

Localized (KZ-301/KZ-304): every bank item carries `text` / `short_text` as
`{locale: str}`; `LOCALES` lists the bank's locales. One logical question =
one row per locale, keyed `(order, locale)`, identical `mi_category` / `order` /
`age_tier` / `icon` across locales.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.profile import AgeGroup
from app.models.question import MIType, Question, QuestionInstrument
from app.services.admin_lock import has_overrides, sync_fields
from scripts.mi_question_bank import LOCALES, QUESTIONS


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        for locale in LOCALES:
            live = [q for q in QUESTIONS if locale in q["text"]]
            live_orders = {q["order"] for q in live}

            existing_result = await db.execute(
                select(Question).where(
                    Question.instrument == QuestionInstrument.mi,
                    Question.locale == locale,
                )
            )
            existing_by_order = {q.order: q for q in existing_result.scalars().all()}

            for data in live:
                category = MIType(data["mi_category"])
                age_tier = AgeGroup(data["age_tier"])
                text = data["text"][locale]
                short_text = (data.get("short_text") or {}).get(locale)
                icon = data.get("icon")

                existing = existing_by_order.get(data["order"])
                if existing is not None:
                    changed = sync_fields(existing, {
                        "mi_category": category,
                        "text": text,
                        "age_tier": age_tier,
                        "short_text": short_text,
                        "icon": icon,
                    })
                    updated += changed
                    skipped += not changed
                    continue

                db.add(
                    Question(
                        instrument=QuestionInstrument.mi,
                        mi_category=category,
                        text=text,
                        order=data["order"],
                        age_tier=age_tier,
                        short_text=short_text,
                        icon=icon,
                        locale=locale,
                    )
                )
                inserted += 1

            for order, question in existing_by_order.items():
                if order not in live_orders and not has_overrides(question):
                    await db.delete(question)
                    deleted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(f"Bank: {len(QUESTIONS)} logical questions x locales {LOCALES}")


if __name__ == "__main__":
    asyncio.run(main())
