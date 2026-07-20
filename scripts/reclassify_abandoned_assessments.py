"""
One-off backfill: before AssessmentStatus.abandoned existed,
assessment_service.create_assessment force-completed any still-in-progress
attempt it superseded — with no reveal ever reached and no feedback ever
given. Those rows sit today as status=completed with no selected_direction_slug
and AssessmentSession.liked IS NULL, and get_current_assessment could hand one
back as "the" assessment, 400-ing every roadmap/result call behind a
confusing "finish the test first" even when an older attempt has a real,
usable result.

This script only relabels status=completed -> status=abandoned for rows that
never received explicit feedback (liked IS NULL) — it never touches rows
where the user actually reached a reveal and answered (liked True or False),
and it never invents or guesses a selected_direction_slug. Idempotent: a
second run finds nothing left to relabel.

Run inside Docker:
    docker-compose exec api python scripts/reclassify_abandoned_assessments.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.assessment import Assessment, AssessmentStatus
from app.models.assessment_session import AssessmentSession


async def main() -> None:
    async with async_session() as db:
        result = await db.execute(
            select(Assessment, AssessmentSession)
            .join(AssessmentSession, AssessmentSession.assessment_id == Assessment.id)
            .where(
                Assessment.status == AssessmentStatus.completed,
                Assessment.selected_direction_slug.is_(None),
                AssessmentSession.liked.is_(None),
            )
        )
        rows = result.all()

        for assessment, _session in rows:
            assessment.status = AssessmentStatus.abandoned

        await db.commit()
        print(f"Reclassified {len(rows)} assessment(s): completed -> abandoned")

        # Assessments with no session row at all predate the akinator engine
        # (old block-based flow) — not this bug's shape, left untouched.
        no_session_result = await db.execute(
            select(Assessment)
            .outerjoin(AssessmentSession, AssessmentSession.assessment_id == Assessment.id)
            .where(
                Assessment.status == AssessmentStatus.completed,
                Assessment.selected_direction_slug.is_(None),
                AssessmentSession.id.is_(None),
            )
        )
        no_session = no_session_result.scalars().all()
        if no_session:
            print(
                f"Note: {len(no_session)} completed/no-selection assessment(s) have no "
                f"AssessmentSession at all (pre-akinator flow) — left untouched."
            )


if __name__ == "__main__":
    asyncio.run(main())
