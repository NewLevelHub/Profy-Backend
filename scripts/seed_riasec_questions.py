"""
Seed script: populate the questions table from riasec_question_bank.py.
Run inside Docker: docker-compose exec api python scripts/seed_riasec_questions.py

Idempotent, self-healing: upserts by `(order, locale)`, deletes any DB row
whose `(order, locale)` is no longer present in QUESTIONS *for that locale* (so
editing riasec_question_bank.py and rerunning this script is the entire "change
the question bank" workflow — nothing else needs touching).

Localized (KZ-301/KZ-302): every bank item carries `text` / `short_text` as
`{locale: str}`; the bank's `LOCALES` lists which locales it ships. One logical
question becomes one row per locale, keyed `(order, locale)`, with identical
structural fields (`riasec_type`, `order`, `age_tier`, `icon`). Each locale's
resync is scoped to its own rows — a locale with no translation for a given
`order` is simply not seeded, and a locale's rows are never deleted because
*another* locale dropped that `order`.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.profile import AgeGroup
from app.models.question import HollandType, Question, QuestionInstrument
from scripts.riasec_question_bank import LOCALES, QUESTIONS


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        for locale in LOCALES:
            # Items that have text for this locale — its live `(order)` set.
            live = [q for q in QUESTIONS if locale in q["text"]]
            live_orders = {q["order"] for q in live}

            # Scoped to instrument='riasec' AND this locale — unscoped would
            # match Big Five rows (same table) or other locales, and the
            # orphan-cleanup below would wrongly delete them.
            existing_result = await db.execute(
                select(Question).where(
                    Question.instrument == QuestionInstrument.riasec,
                    Question.locale == locale,
                )
            )
            existing_by_order = {q.order: q for q in existing_result.scalars().all()}

            for data in live:
                riasec_type = HollandType(data["riasec_type"])
                age_tier = AgeGroup(data["age_tier"])
                text = data["text"][locale]
                short_text = (data.get("short_text") or {}).get(locale)
                icon = data.get("icon")

                existing = existing_by_order.get(data["order"])
                if existing is not None:
                    changed = False
                    if existing.riasec_type != riasec_type:
                        existing.riasec_type = riasec_type
                        changed = True
                    if existing.text != text:
                        existing.text = text
                        changed = True
                    if existing.age_tier != age_tier:
                        existing.age_tier = age_tier
                        changed = True
                    if existing.short_text != short_text:
                        existing.short_text = short_text
                        changed = True
                    if existing.icon != icon:
                        existing.icon = icon
                        changed = True
                    updated += changed
                    skipped += not changed
                    continue

                db.add(Question(
                    riasec_type=riasec_type, text=text, order=data["order"],
                    age_tier=age_tier, short_text=short_text, icon=icon, locale=locale,
                ))
                inserted += 1

            for order, question in existing_by_order.items():
                if order not in live_orders:
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
