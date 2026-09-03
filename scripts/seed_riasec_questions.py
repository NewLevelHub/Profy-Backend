"""
Seed script: populate the questions table from riasec_question_bank.py.
Run inside Docker: docker-compose exec api python scripts/seed_riasec_questions.py

Idempotent, self-healing: upserts by `order`, deletes any DB row whose `order`
is no longer present in QUESTIONS (so editing riasec_question_bank.py and
rerunning this script is the entire "change the question bank" workflow —
nothing else needs touching).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.profile import AgeGroup
from app.models.question import HollandType, Question, QuestionInstrument
from app.services.admin_lock import has_overrides, sync_fields
from scripts.riasec_question_bank import QUESTIONS


async def main() -> None:
    async with async_session() as db:
        live_orders = {q["order"] for q in QUESTIONS}

        # Scoped to instrument='riasec' — unscoped would also match Big Five
        # rows (same table) and the orphan-cleanup below would wrongly delete
        # every one of them, since their `order` is never in RIASEC's own
        # live_orders.
        existing_result = await db.execute(
            select(Question).where(Question.instrument == QuestionInstrument.riasec)
        )
        existing_by_order = {q.order: q for q in existing_result.scalars().all()}

        inserted = 0
        updated = 0
        skipped = 0
        deleted = 0

        for data in QUESTIONS:
            existing = existing_by_order.get(data["order"])
            riasec_type = HollandType(data["riasec_type"])
            age_tier = AgeGroup(data["age_tier"])

            short_text = data.get("short_text")
            icon = data.get("icon")

            if existing is not None:
                changed = sync_fields(existing, {
                    "riasec_type": riasec_type,
                    "text": data["text"],
                    "age_tier": age_tier,
                    "short_text": short_text,
                    "icon": icon,
                })
                if changed:
                    updated += 1
                else:
                    skipped += 1
                continue

            db.add(Question(
                riasec_type=riasec_type, text=data["text"], order=data["order"], age_tier=age_tier,
                short_text=short_text, icon=icon,
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
        print(f"Total questions in bank: {len(QUESTIONS)}")


if __name__ == "__main__":
    asyncio.run(main())
