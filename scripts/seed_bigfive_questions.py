"""
Seed script: populate the questions table (Big Five rows) from
bigfive_question_bank.py.
Run inside Docker, AFTER seed_riasec_questions.py (order continues from the
RIASEC bank's length): docker-compose exec api python scripts/seed_bigfive_questions.py

Idempotent, self-healing: upserts by `(order, locale)`, deletes any big_five DB
row whose `(order, locale)` is no longer present in QUESTIONS *for that locale*
— same pattern as seed_riasec_questions.py. Only touches instrument='big_five'.

Localized (KZ-301/KZ-303): every bank item carries `text` / `short_text` as
`{locale: str}`; `LOCALES` lists which locales the bank ships. One logical
question becomes one row per locale, keyed `(order, locale)`, with identical
structural fields (`bigfive_domain`, `facet`, `keyed`, `order`, `age_tier`,
`icon`). Each locale's resync is scoped to its own rows.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.profile import AgeGroup
from app.models.question import BigFiveDomain, Keyed, Question, QuestionInstrument
from scripts.bigfive_question_bank import LOCALES, QUESTIONS


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        for locale in LOCALES:
            live = [q for q in QUESTIONS if locale in q["text"]]
            live_orders = {q["order"] for q in live}

            existing_result = await db.execute(
                select(Question).where(
                    Question.instrument == QuestionInstrument.big_five,
                    Question.locale == locale,
                )
            )
            existing_by_order = {q.order: q for q in existing_result.scalars().all()}

            for data in live:
                domain = BigFiveDomain(data["bigfive_domain"])
                keyed = Keyed(data["keyed"])
                age_tier = AgeGroup(data["age_tier"])
                text = data["text"][locale]
                short_text = (data.get("short_text") or {}).get(locale)
                icon = data.get("icon")

                existing = existing_by_order.get(data["order"])
                if existing is not None:
                    changed = False
                    if existing.bigfive_domain != domain:
                        existing.bigfive_domain = domain
                        changed = True
                    if existing.facet != data["facet"]:
                        existing.facet = data["facet"]
                        changed = True
                    if existing.keyed != keyed:
                        existing.keyed = keyed
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
                        locale=locale,
                    )
                )
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
