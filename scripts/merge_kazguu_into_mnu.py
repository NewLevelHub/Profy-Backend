"""One-time fix for a duplicate that predates the jinaq import entirely:
KAZGUU University was renamed to Maqsut Narikbayev University, but both the
old name (slug `kazgyuu`) and the new one (slug `mnu`) existed as separate
University rows in the curated dataset. Confirmed by the project owner —
same real institution.

`mnu` is kept (current name, already has the jinaq-sourced photo from
scripts/apply_kz_university_merge.py); `kazgyuu`'s programs are moved over
(name collisions are dropped as redundant, same rule as
apply_kz_university_merge.py) and the row is deleted.

Idempotent: a second run finds `kazgyuu` already gone and does nothing.

Run inside the api container:
  docker-compose exec api python scripts/merge_kazguu_into_mnu.py [--dry-run]
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


async def main(*, dry_run: bool) -> None:
    async with async_session() as db:
        old = (await db.execute(select(University).where(University.slug == "kazgyuu"))).scalar_one_or_none()
        new = (await db.execute(select(University).where(University.slug == "mnu"))).scalar_one_or_none()

        if old is None:
            print("kazgyuu already merged (or never existed) — nothing to do")
            return
        if new is None:
            print("ERROR: mnu not found, aborting")
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

        print(f"Moved {moved} programs, dropped {dropped} as duplicates, moved {len(images)} photo(s), deleted kazgyuu")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
