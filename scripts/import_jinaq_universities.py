"""Imports the jinaq world university directory
(scripts/data/jinaq/universities.json — 2313 universities across 32
countries, 10,113 majors, source site "jinaq") into University/Program.

Links each jinaq institution to an existing University row by exact match on
normalized (name, city, country) — no fuzzy matching, same discipline as
scripts/apply_ovpo_codes.py (whose own fuzzy-matching attempt produced false
positives, e.g. matching "Satbayev University" to "SDU University", and was
discarded in favor of only trusting exact/hand-checked matches). Most of the
~2211 non-Kazakhstan institutions are expected to have no existing match at
all — that's the normal, desired outcome here (not a failure to flag for
review): a new University row is created for them. Only the ~102 Kazakhstan
institutions are expected to mostly land on existing rows.

Idempotent and resumable: commits once per institution (not one giant
transaction) and looks up scripts/data/jinaq/universities.json's institution
id in university_external_refs *first*, before any name-matching — so a
re-run (including one resuming after a crash partway through) always
resolves a given source id to the same university_id, and never re-creates a
duplicate row for it.

Deliberately does NOT touch price/cost — Program.cost_per_year/cost_currency
are left untouched (None); the frontend handles pricing separately, out of
scope here.

Enriches existing University rows without ever overwriting curated content:
`description` is filled only if currently empty; `contacts`/`facilities`
gain new keys (email/phone/address/has_dormitory) without touching whatever
is already there.

majors -> Program relies on the existing (university_id, name_normalized)
unique constraint for idempotency (no new columns needed for that). A name
collision (e.g. a duplicate-named major already present, or two majors in
the source that normalize the same way) is treated as "already exists" and
skipped via a per-row SAVEPOINT, not an error that aborts the batch — a
known, accepted trade-off: majors on already-curated Kazakhstan universities
are named in Russian there and in English here, so they will NOT collide and
will be added as separate Program rows alongside the curated ones (see
scripts/merge_duplicate_programs.py for the tool that cleaned up an earlier,
similar situation, if this ever needs the same cleanup).

`Program.requirements` is populated only under keys already understood by
app/services/university_requirements.py::map_program_requirement — no
changes needed there: `duration_years` (from major.durationYears), and
`min_ielts`/`notes` derived from the institution-level `enrollmentRequirements`/
`enrollmentDocuments` (the same values are reused for every major at that
institution, since the source data is institution-wide, not per-major —
matching this codebase's existing convention documented in that module).

Run inside the api container:
  docker-compose exec api python scripts/import_jinaq_universities.py [--dry-run] [--limit N]
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from scripts.seed_riasec_directions import slugify

SOURCE_NAME = "jinaq"
DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jinaq", "universities.json")


def _normalize(text: str | None) -> str:
    return " ".join((text or "").strip().lower().split())


def _slug_for(name: str, taken_slugs: set[str]) -> str:
    base = slugify(name) or "university"
    slug = base
    suffix = 2
    while slug in taken_slugs:
        slug = f"{base}-{suffix}"
        suffix += 1
    taken_slugs.add(slug)
    return slug


def _requirement_notes_and_ielts(
    enrollment_requirements: list[dict], enrollment_documents: list[dict]
) -> tuple[list[str], float | None]:
    """institution-wide facts, reused for every major at that institution —
    see module docstring for why that's consistent with this codebase's
    existing convention rather than a shortcut."""
    min_ielts: float | None = None
    notes: list[str] = []
    for req in enrollment_requirements:
        name = req.get("name") or ""
        value = req.get("value")
        if min_ielts is None and "ielts" in name.lower():
            try:
                min_ielts = float(value)
                continue
            except (TypeError, ValueError):
                pass
        notes.append(f"{name}: {value}" if value not in (None, "") else name)
    for doc in enrollment_documents:
        name = doc.get("name")
        if name:
            notes.append(f"Требуемый документ: {name}")
    return notes, min_ielts


async def _find_or_create_university(
    db: AsyncSession,
    *,
    institution: dict,
    ref_by_external_id: dict[str, UniversityExternalRef],
    existing_by_key: dict[tuple[str, str, str], University],
    taken_slugs: set[str],
) -> tuple[University, bool]:
    """Returns (university, created). Checks university_external_refs first
    so a re-run resolves the same institution to the same University
    regardless of what name-matching alone would produce this time."""
    external_id = str(institution["id"])
    ref = ref_by_external_id.get(external_id)
    if ref is not None:
        result = await db.execute(select(University).where(University.id == ref.university_id))
        return result.scalar_one(), False

    name = institution["name"]
    city = (institution.get("city") or {}).get("name") or ""
    country = (institution.get("country") or {}).get("name") or ""
    key = (_normalize(name), _normalize(city), _normalize(country))

    existing = existing_by_key.get(key)
    if existing is not None:
        return existing, False

    slug = _slug_for(name, taken_slugs)
    new_university = University(
        name=name,
        slug=slug,
        short_name=institution.get("shortName") or None,
        aliases=[],
        country=country,
        city=city,
        website=institution.get("website") or None,
        description=institution.get("description") or None,
    )
    db.add(new_university)
    await db.flush()
    existing_by_key[key] = new_university
    return new_university, True


def _enrich_university(university: University, institution: dict) -> bool:
    """Fills gaps without overwriting curated content. Returns True if
    anything actually changed (for the dry-run/real-run summary counters)."""
    changed = False

    if not university.description and institution.get("description"):
        university.description = institution["description"]
        changed = True

    contacts = dict(university.contacts or {})
    if institution.get("email") and "email" not in contacts:
        contacts["email"] = institution["email"]
        changed = True
    if institution.get("contactNumber") and "phone" not in contacts:
        contacts["phone"] = institution["contactNumber"]
        changed = True
    if institution.get("address") and "address" not in contacts:
        contacts["address"] = institution["address"]
        changed = True
    university.contacts = contacts

    facilities = dict(university.facilities or {})
    if "hasDorm" in institution and "has_dormitory" not in facilities:
        facilities["has_dormitory"] = bool(institution["hasDorm"])
        facilities_changed = True
    else:
        facilities_changed = False
    university.facilities = facilities
    changed = changed or facilities_changed

    if changed:
        university.updated_at = datetime.now(timezone.utc)
    return changed


async def _import_majors(db: AsyncSession, *, university: University, institution: dict) -> tuple[int, int]:
    notes, min_ielts = _requirement_notes_and_ielts(
        institution.get("enrollmentRequirements") or [],
        institution.get("enrollmentDocuments") or [],
    )
    created = skipped = 0
    for major in institution.get("majors") or []:
        requirements: dict = {}
        if major.get("durationYears") is not None:
            requirements["duration_years"] = major["durationYears"]
        if min_ielts is not None:
            requirements["min_ielts"] = min_ielts
        if notes:
            requirements["notes"] = notes

        try:
            async with db.begin_nested():
                db.add(
                    Program(
                        university_id=university.id,
                        name=major["name"],
                        language=major.get("learningLanguage") or "",
                        source_category=major.get("category"),
                        requirements=requirements,
                    )
                )
                await db.flush()
            created += 1
        except IntegrityError:
            skipped += 1
    return created, skipped


async def main(*, dry_run: bool, limit: int | None) -> None:
    with open(DATA_PATH, encoding="utf-8") as f:
        institutions: list[dict] = json.load(f)
    if limit:
        institutions = institutions[:limit]

    async with async_session() as db:
        refs_result = await db.execute(
            select(UniversityExternalRef).where(UniversityExternalRef.source == SOURCE_NAME)
        )
        ref_by_external_id = {ref.external_id: ref for ref in refs_result.scalars().all()}

        all_unis_result = await db.execute(select(University))
        all_unis = list(all_unis_result.scalars().all())
        existing_by_key = {
            (_normalize(u.name), _normalize(u.city), _normalize(u.country)): u for u in all_unis
        }
        taken_slugs = {u.slug for u in all_unis if u.slug}

        universities_created = universities_enriched = universities_unchanged = 0
        programs_created = programs_skipped = 0
        failed: list[tuple[str, str]] = []

        for institution in institutions:
            try:
                university, created = await _find_or_create_university(
                    db,
                    institution=institution,
                    ref_by_external_id=ref_by_external_id,
                    existing_by_key=existing_by_key,
                    taken_slugs=taken_slugs,
                )
                if created:
                    universities_created += 1
                elif _enrich_university(university, institution):
                    universities_enriched += 1
                else:
                    universities_unchanged += 1

                external_id = str(institution["id"])
                if external_id not in ref_by_external_id:
                    ref = UniversityExternalRef(
                        source=SOURCE_NAME,
                        external_id=external_id,
                        external_name=institution["name"],
                        university_id=university.id,
                        match_method="new" if created else "exact",
                        matched_at=datetime.now(timezone.utc),
                    )
                    db.add(ref)
                    ref_by_external_id[external_id] = ref

                created_count, skipped_count = await _import_majors(db, university=university, institution=institution)
                programs_created += created_count
                programs_skipped += skipped_count

                if not dry_run:
                    await db.commit()
            except Exception as exc:  # noqa: BLE001 — one bad record must not abort the batch
                await db.rollback()
                failed.append((str(institution.get("id")), repr(exc)))

        if dry_run:
            await db.rollback()
            print("[dry-run] no changes committed")

        print(
            f"Universities — created: {universities_created}, enriched: {universities_enriched}, "
            f"unchanged: {universities_unchanged}"
        )
        print(f"Programs — created: {programs_created}, skipped (duplicate name): {programs_skipped}")
        if failed:
            print(f"Failed ({len(failed)}):")
            for external_id, reason in failed:
                print(f"  {external_id}: {reason}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, limit=args.limit))
