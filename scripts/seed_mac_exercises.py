"""
Seed script: upsert `mac_exercises` from mac_exercise_bank.py (PRO-315).

Run inside Docker:
    docker-compose exec api python scripts/seed_mac_exercises.py

Idempotent, self-healing on `code` (E1..E6): inserts new rows, overwrites
changed fields on existing ones. Never deletes — `mac_responses.exercise_id`
is RESTRICT, and a code dropped from the bank should stop being offered, not
break history; such rows are just left `active=False`.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.mac import MacDrawMode, MacExercise
from scripts.mac_exercise_bank import MAC_EXERCISES

_FIELDS = (
    "order", "title", "stimulus_question", "spread_size", "pick_count",
    "followup_questions", "subjects", "active",
)


async def main() -> None:
    bank_codes = {e["code"] for e in MAC_EXERCISES}

    async with async_session() as db:
        existing = (await db.execute(select(MacExercise))).scalars().all()
        by_code = {e.code: e for e in existing}

        inserted = updated = 0
        for data in MAC_EXERCISES:
            exercise = by_code.get(data["code"])
            if exercise is None:
                db.add(MacExercise(
                    code=data["code"],
                    draw_mode=MacDrawMode(data["draw_mode"]),
                    **{k: data[k] for k in _FIELDS},
                ))
                inserted += 1
                continue

            changed = False
            if exercise.draw_mode.value != data["draw_mode"]:
                exercise.draw_mode = MacDrawMode(data["draw_mode"])
                changed = True
            for field in _FIELDS:
                if getattr(exercise, field) != data[field]:
                    setattr(exercise, field, data[field])
                    changed = True
            if changed:
                updated += 1

        deactivated = 0
        for exercise in existing:
            if exercise.code not in bank_codes and exercise.active:
                exercise.active = False
                deactivated += 1

        await db.commit()

    print(f"mac_exercises: {inserted} inserted, {updated} updated, {deactivated} deactivated")


if __name__ == "__main__":
    asyncio.run(main())
