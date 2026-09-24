"""
Seed script: populate the questions table from riasec_question_bank.py.
Run inside Docker: docker-compose exec api python scripts/seed_riasec_questions.py

Idempotent, self-healing: upserts by `order`, deletes any riasec DB row whose
`order` is no longer present in QUESTIONS (so editing riasec_question_bank.py
and rerunning this script is the entire "change the question bank" workflow —
nothing else needs touching).

Localized (single-row redesign, docs/i18n-contract.md §8): one logical
question = one row, `text`/`short_text` stored whole as their bank
`{locale: str}` maps.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.question import LOCALIZED_FIELDS, HollandType, Question, QuestionInstrument
from app.services.admin_lock import has_overrides, sync_fields
from scripts.riasec_question_bank import QUESTIONS


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        live_orders = {q["order"] for q in QUESTIONS}

        # Scoped to instrument='riasec' — unscoped would match Big Five/MI
        # rows (same table) and the orphan-cleanup below would wrongly delete
        # them.
        existing_result = await db.execute(
            select(Question).where(Question.instrument == QuestionInstrument.riasec)
        )
        existing_by_order = {q.order: q for q in existing_result.scalars().all()}

        for data in QUESTIONS:
            riasec_type = HollandType(data["riasec_type"])
            text = data["text"]
            short_text = data.get("short_text")
            icon = data.get("icon")

            existing = existing_by_order.get(data["order"])
            if existing is not None:
                changed = sync_fields(
                    existing,
                    {
                        "riasec_type": riasec_type,
                        "text": text,
                        "short_text": short_text,
                        "icon": icon,
                    },
                    localized_fields=LOCALIZED_FIELDS,
                )
                updated += changed
                skipped += not changed
                continue

            db.add(Question(
                riasec_type=riasec_type, text=text, order=data["order"],
                short_text=short_text, icon=icon,
                instrument=QuestionInstrument.riasec,
            ))
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
        print(f"Bank: {len(QUESTIONS)} logical questions")


if __name__ == "__main__":
    asyncio.run(main())
