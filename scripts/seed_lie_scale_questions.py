"""
Seed script: populate the questions table with protocol-validity rows
(instrument='validity') from lie_scale_bank.py (20 MC-SDS items) +
infrequency_bank.py (3-5 attention-check traps). Epic PRO-282, phase 1;
PRO-297 data model, PRO-298 battery integration.

Run inside Docker, AFTER seed_bigfive_questions.py / seed_mi_questions.py
(the banks derive their `order` from those banks' lengths):
    docker-compose exec api python scripts/seed_lie_scale_questions.py

Idempotent, self-healing: upserts by `order`, deletes any validity DB row
whose `order` is no longer in the banks — same pattern as
seed_bigfive_questions.py. Only touches instrument='validity' rows; the
Big Five / RIASEC / MI battery is untouched. `order` here is only a stable
id — the runtime presentation position is decided per-assessment by
app/services/validity_battery.py (PRO-298), not by this number.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument, ValidityRole
from app.services.admin_lock import has_overrides, sync_fields
from scripts.infrequency_bank import ITEMS as INFREQUENCY_ITEMS
from scripts.lie_scale_bank import ITEMS as MC_SDS_ITEMS

ITEMS: list[dict] = [*MC_SDS_ITEMS, *INFREQUENCY_ITEMS]


def _validity_meta(data: dict) -> dict:
    """Per-role scoring payload stored on Question.validity_meta. `key` is the
    stable bank code (mc_sds_01 / infreq_01) so validity_service (PRO-299) can
    address each item in its `details` breakdown."""
    if data["validity_role"] == "sd_key":
        return {"key": data["key"], "keyed": data["keyed"]}
    return {"key": data["key"], "expected_answer": data["expected_answer"]}


async def main() -> None:
    async with async_session() as db:
        live_orders = {item["order"] for item in ITEMS}

        existing_result = await db.execute(
            select(Question).where(Question.instrument == QuestionInstrument.validity)
        )
        existing_by_order = {q.order: q for q in existing_result.scalars().all()}

        inserted = updated = skipped = deleted = 0

        for data in ITEMS:
            role = ValidityRole(data["validity_role"])
            age_tier = AgeGroup(data["age_tier"])
            meta = _validity_meta(data)
            existing = existing_by_order.get(data["order"])

            if existing is not None:
                changed = sync_fields(existing, {
                    "validity_role": role,
                    "validity_meta": meta,
                    "text": data["text"],
                    "age_tier": age_tier,
                })
                updated += 1 if changed else 0
                skipped += 0 if changed else 1
                continue

            db.add(
                Question(
                    instrument=QuestionInstrument.validity,
                    validity_role=role,
                    validity_meta=meta,
                    text=data["text"],
                    order=data["order"],
                    age_tier=age_tier,
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
        print(
            f"Total validity items in banks: {len(ITEMS)} "
            f"({len(MC_SDS_ITEMS)} MC-SDS + {len(INFREQUENCY_ITEMS)} infrequency)"
        )


if __name__ == "__main__":
    asyncio.run(main())
