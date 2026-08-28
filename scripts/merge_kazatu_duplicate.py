"""One-time fix for a duplicate discovered while auditing which universities
still had zero photos: "Казахский агротехнический университет (КазАТУ)"
(slug `kazahskij-agrotehnicheskij-universitet-kazatu`, city "Алматы") in
university-data/almaty_universities_data.py is the same real institution as
"Казахский агротехнический исследовательский университет им. С. Сейфуллина"
(slug `kazatu`, ovpo_code 002, correctly in Астана) — same website
(kazatu.edu.kz), just filed under the wrong city with an outdated name in
the Almaty source data. Removed from that source file already; this merges
the DB row it created.

`kazatu` is kept (has ovpo_code, more programs, the jinaq-sourced photo);
the duplicate's 14 programs are moved over (name collisions dropped as
redundant, same rule as every other merge script in this project).

Idempotent: a second run finds the duplicate slug already gone and does
nothing.

Run inside the api container:
  docker-compose exec api python scripts/merge_kazatu_duplicate.py [--dry-run]
"""
import argparse
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from app.models.university_image import UniversityImage

OLD_SLUG = "kazahskij-agrotehnicheskij-universitet-kazatu"
NEW_SLUG = "kazatu"


async def main(*, dry_run: bool) -> None:
    async with async_session() as db:
        old = (await db.execute(select(University).where(University.slug == OLD_SLUG))).scalar_one_or_none()
        new = (await db.execute(select(University).where(University.slug == NEW_SLUG))).scalar_one_or_none()

        if old is None:
            print(f"{OLD_SLUG} already merged (or never existed) — nothing to do")
            return
        if new is None:
            print(f"ERROR: {NEW_SLUG} not found, aborting")
            return

        new_has_primary = (
            await db.execute(
                select(UniversityImage).where(UniversityImage.university_id == new.id, UniversityImage.is_primary.is_(True))
            )
        ).scalar_one_or_none() is not None

        images = (await db.execute(select(UniversityImage).where(UniversityImage.university_id == old.id))).scalars().all()
        for image in images:
            image.university_id = new.id
            if image.is_primary and new_has_primary:
                image.is_primary = False
            elif image.is_primary:
                new_has_primary = True

        moved = dropped = 0
        programs = (await db.execute(select(Program).where(Program.university_id == old.id))).scalars().all()
        for program in programs:
            try:
                async with db.begin_nested():
                    program.university_id = new.id
                    await db.flush()
                moved += 1
            except IntegrityError:
                await db.delete(program)
                await db.flush()
                dropped += 1

        refs = (await db.execute(select(UniversityExternalRef).where(UniversityExternalRef.university_id == old.id))).scalars().all()
        for ref in refs:
            ref.university_id = new.id

        await db.execute(delete(University).where(University.id == old.id))

        if dry_run:
            await db.rollback()
            print("[dry-run] no changes committed")
        else:
            await db.commit()

        print(f"Moved {moved} programs, dropped {dropped} as duplicates, moved {len(images)} photo(s), deleted {OLD_SLUG}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
