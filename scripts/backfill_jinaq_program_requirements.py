"""One-time fix for Program rows already created by
scripts/import_jinaq_universities.py before it separated `notes` from
`source_required_documents` — previously both enrollmentRequirements AND
enrollmentDocuments were dumped into `requirements.notes`, and since jinaq's
own data restates the same admission facts in both lists for most foreign
universities (checked across Canada/UK/Malaysia — same template), that read
as literal duplication on the program-detail page ("Доказательство владения
английским..." + "Требуемый документ: Результаты языкового теста...").

Re-running scripts/import_jinaq_universities.py does NOT fix already-created
rows — it only inserts new ones and skips existing ones on a name conflict.
This script instead UPDATEs `requirements` in place for every jinaq-sourced
Program, recomputing notes/min_ielts/source_required_documents fresh from
the same source file with the corrected split. Only touches
`requirements` — never touches directions, description, or anything else
that scripts/apply_jinaq_specialty_directions.py or manual edits may have
since added.

Idempotent: recomputing and overwriting `requirements` with the same
correct values is a no-op on a second run.

Run inside the api container:
  docker-compose exec api python scripts/backfill_jinaq_program_requirements.py [--dry-run]
"""
import argparse
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university_external_ref import UniversityExternalRef
from scripts.import_jinaq_universities import DATA_PATH, SOURCE_NAME, _requirement_notes_and_ielts


async def main(*, dry_run: bool) -> None:
    with open(DATA_PATH, encoding="utf-8") as f:
        institutions: list[dict] = json.load(f)

    async with async_session() as db:
        refs_result = await db.execute(
            select(UniversityExternalRef).where(UniversityExternalRef.source == SOURCE_NAME)
        )
        university_id_by_external_id = {ref.external_id: ref.university_id for ref in refs_result.scalars().all()}

        updated = programs_seen = 0
        for institution in institutions:
            university_id = university_id_by_external_id.get(str(institution["id"]))
            if university_id is None:
                continue

            notes, min_ielts, required_documents = _requirement_notes_and_ielts(
                institution.get("enrollmentRequirements") or [],
                institution.get("enrollmentDocuments") or [],
            )

            majors = institution.get("majors") or []
            if not majors:
                continue

            names = [m["name"] for m in majors]
            programs_result = await db.execute(
                select(Program).where(Program.university_id == university_id, Program.name.in_(names))
            )
            for program in programs_result.scalars().all():
                programs_seen += 1
                major = next((m for m in majors if m["name"] == program.name), None)
                requirements: dict = {}
                if major and major.get("durationYears") is not None:
                    requirements["duration_years"] = major["durationYears"]
                if min_ielts is not None:
                    requirements["min_ielts"] = min_ielts
                if notes:
                    requirements["notes"] = notes
                if required_documents:
                    requirements["source_required_documents"] = required_documents

                if program.requirements != requirements:
                    program.requirements = requirements
                    updated += 1

        if dry_run:
            await db.rollback()
            print("[dry-run] no changes committed")
        else:
            await db.commit()

        print(f"Programs checked: {programs_seen}, updated: {updated}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
