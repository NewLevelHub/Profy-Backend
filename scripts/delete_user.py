"""
Permanently delete a Profy user and all their data.
Run: docker-compose exec api python scripts/delete_user.py user@example.com

Deletes, in FK-safe order (profiles.user_id and artifacts.profile_id have
no ON DELETE CASCADE, unlike everything under assessments):
  1. artifacts (by profile_id)
  2. assessments (by profile_id) — cascades to analysis_results,
     direction_roadmap, assessment_session, subject_readiness_session,
     profession_simulation_log, known_profession_quiz_log; nulls out
     product_feedback.assessment_id
  3. profile
  4. user — cascades to password_resets, email_verifications,
     product_feedback (by user_id), psychologist_student_assignments
     (as psychologist_id or student_id), psychologist_notes
     (as psychologist_id or student_id)
All in one transaction: either everything goes, or nothing does.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select

from app.database import async_session
from app.models.artifact import Artifact
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/delete_user.py <email>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"User not found: {email}")
            sys.exit(1)

        profile_result = await db.execute(select(Profile).where(Profile.user_id == user.id))
        profile = profile_result.scalar_one_or_none()

        if profile:
            await db.execute(delete(Artifact).where(Artifact.profile_id == profile.id))
            await db.execute(delete(Assessment).where(Assessment.profile_id == profile.id))
            await db.delete(profile)

        await db.delete(user)
        await db.commit()
        print(f"Deleted {email}" + (" (with profile and all related data)" if profile else " (no profile existed)"))


if __name__ == "__main__":
    asyncio.run(main())
