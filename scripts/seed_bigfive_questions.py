"""
Seed script: populate the questions table (Big Five rows) from
bigfive_question_bank.py.
Run inside Docker, AFTER seed_riasec_questions.py (order continues from the
RIASEC bank's length): docker-compose exec api python scripts/seed_bigfive_questions.py

Idempotent, self-healing: upserts by `order`, deletes any big_five DB row
whose `order` is no longer present in QUESTIONS — same pattern as
seed_riasec_questions.py. Only touches instrument='big_five'.
Admin-overridden fields/rows are preserved (admin_lock.sync_fields / has_overrides).

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
from app.models.profile import AgeGroup
from app.models.question import LOCALIZED_FIELDS, BigFiveDomain, Keyed, Question, QuestionInstrument
from app.services.admin_lock import has_overrides, sync_fields
from scripts.bigfive_question_bank import QUESTIONS


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        live_orders = {q["order"] for q in QUESTIONS}

        existing_result = await db.execute(
            select(Question).where(Question.instrument == QuestionInstrument.big_five)
        )
        existing_by_order = {q.order: q for q in existing_result.scalars().all()}

        for data in QUESTIONS:
            domain = BigFiveDomain(data["bigfive_domain"])
            keyed = Keyed(data["keyed"])
            age_tier = AgeGroup(data["age_tier"])
            text = data["text"]
            short_text = data.get("short_text")
            icon = data.get("icon")

            existing = existing_by_order.get(data["order"])
            if existing is not None:
                changed = sync_fields(
                    existing,
                    {
                        "bigfive_domain": domain,
                        "facet": data["facet"],
                        "keyed": keyed,
                        "text": text,
                        "age_tier": age_tier,
                        "short_text": short_text,
                        "icon": icon,
                    },
                    localized_fields=LOCALIZED_FIELDS,
                )
                updated += changed
                skipped += not changed
                continue

            db.add(
                Question(
                    instrument=QuestionInstrument.big_five,
                    bigfive_domain=domain,
                    facet=data["facet"],
                    keyed=keyed,
                    text=text,
                    order=data["order"],
                    age_tier=age_tier,
                    short_text=short_text,
                    icon=icon,
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
        print(f"Bank: {len(QUESTIONS)} logical questions")


if __name__ == "__main__":
    asyncio.run(main())
