"""Builds the careers' «Почему тебе подходит» (AnalysisResult.career_fit) for
reports that have none yet or were built under an older
app/data/career_fit_rules.json version.

Reads every instrument again (career_fit_service.build_for_rows), never
regenerates a report and never touches anything the psychologist reviewed —
career fit is system text next to the careers, not part of them. All locale
rows of an assessment get the same locale-free result. Idempotent: rows that
are already current are skipped, so running it on every deploy is a no-op
once done. Their cached /result payloads are dropped so the change shows up
right away.

Run inside Docker: docker compose exec api python scripts/backfill_career_fit.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.analysis_result import AnalysisResult
from app.services import assessment_shared, career_fit_service


async def main() -> None:
    updated: list = []
    async with async_session() as db:
        rows = (await db.execute(select(AnalysisResult))).scalars().all()
        by_assessment: dict = {}
        for row in rows:
            by_assessment.setdefault(row.assessment_id, []).append(row)
        for assessment_id, group in by_assessment.items():
            if all(career_fit_service.is_current(row.career_fit) for row in group):
                continue
            try:
                fresh = await career_fit_service.build_for_rows(group, db)
            except Exception as exc:  # noqa: BLE001 — one broken report must not fail the deploy
                print(f"skipped assessment {assessment_id}: {exc!r}")
                continue
            for row in group:
                row.career_fit = fresh
            updated.append(assessment_id)
        await db.commit()

    redis = assessment_shared.get_redis()
    for assessment_id in updated:
        await assessment_shared.safe_redis_delete(redis, *assessment_shared.report_cache_keys(assessment_id))
    print(f"Career fit built for {len(updated)} assessment(s)")


if __name__ == "__main__":
    asyncio.run(main())
