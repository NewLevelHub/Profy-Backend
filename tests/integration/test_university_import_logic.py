"""Exercises the find-or-create/enrich/major-import logic in
scripts/import_jinaq_universities.py directly against a real, per-test
rolled-back DB session (see tests/conftest.py) — no HTTP, no file I/O,
since neither is what this logic does."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.program import Program
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from scripts.import_jinaq_universities import (
    _enrich_university,
    _find_or_create_university,
    _import_majors,
    _requirement_notes_and_ielts,
)


def _institution(**overrides: object) -> dict:
    base = {
        "id": 12345,
        "name": "Test University",
        "shortName": "TU",
        "description": "A test university.",
        "website": "https://test.example",
        "email": "info@test.example",
        "contactNumber": "+1 555 0100",
        "address": "1 Test St",
        "hasDorm": True,
        "city": {"name": "Testville"},
        "country": {"name": "Testland"},
        "majors": [],
        "enrollmentDocuments": [],
        "enrollmentRequirements": [],
    }
    base.update(overrides)
    return base


async def test_creates_new_university_when_no_match(db_session: AsyncSession):
    institution = _institution()
    university, created = await _find_or_create_university(
        db_session,
        institution=institution,
        ref_by_external_id={},
        existing_by_key={},
        taken_slugs=set(),
    )
    assert created is True
    assert university.name == "Test University"
    assert university.city == "Testville"
    assert university.country == "Testland"
    assert university.slug


async def test_finds_existing_university_by_exact_name_city_country(db_session: AsyncSession):
    existing = University(
        name="Existing University", slug="existing-university",
        aliases=[], country="Testland", city="Testville",
    )
    db_session.add(existing)
    await db_session.flush()

    institution = _institution(name="Existing University")
    key = ("existing university", "testville", "testland")

    university, created = await _find_or_create_university(
        db_session,
        institution=institution,
        ref_by_external_id={},
        existing_by_key={key: existing},
        taken_slugs={"existing-university"},
    )
    assert created is False
    assert university.id == existing.id


async def test_second_lookup_via_external_ref_is_idempotent(db_session: AsyncSession):
    """A re-run must resolve the same source id to the same university_id
    regardless of what name-matching alone would produce this time."""
    existing = University(
        name="Renamed University", slug="renamed-university",
        aliases=[], country="Testland", city="Testville",
    )
    db_session.add(existing)
    await db_session.flush()

    ref = UniversityExternalRef(
        source="jinaq", external_id="12345", university_id=existing.id, match_method="new",
    )
    db_session.add(ref)
    await db_session.flush()

    # Name in the source no longer matches the (now-renamed) DB row at all —
    # a name-based lookup would fail to find it, but the ref must win.
    institution = _institution(name="Totally Different Name Now")
    university, created = await _find_or_create_university(
        db_session,
        institution=institution,
        ref_by_external_id={"12345": ref},
        existing_by_key={},
        taken_slugs=set(),
    )
    assert created is False
    assert university.id == existing.id


def test_enrich_fills_empty_description_but_never_overwrites():
    university = University(name="X", slug="x", aliases=[], country="C", city="Y", description=None)
    changed = _enrich_university(university, _institution(description="From source"))
    assert changed is True
    assert university.description == "From source"

    # Second call with a different source description must not clobber it.
    changed_again = _enrich_university(university, _institution(description="Different text"))
    assert university.description == "From source"
    assert changed_again is False


def test_enrich_merges_contacts_and_facilities_without_clobbering_existing():
    university = University(
        name="X", slug="x", aliases=[], country="C", city="Y",
        contacts={"email": "already@set.example"}, facilities={"has_dormitory": False},
    )
    changed = _enrich_university(university, _institution(email="new@source.example", hasDorm=True))
    assert changed is True
    # Existing keys are untouched — only genuinely missing keys are added.
    assert university.contacts["email"] == "already@set.example"
    assert university.facilities["has_dormitory"] is False
    assert university.contacts["phone"] == "+1 555 0100"
    assert university.contacts["address"] == "1 Test St"


def test_requirement_notes_and_ielts_extracts_ielts_and_formats_rest():
    notes, min_ielts, required_documents = _requirement_notes_and_ielts(
        enrollment_requirements=[
            {"name": "Минимальный IELTS", "type": "LANGUAGE", "value": "6.0"},
            {"name": "Минимальный TOEFL", "type": "LANGUAGE", "value": "75"},
        ],
        enrollment_documents=[{"id": 1, "name": "IELTS"}],
    )
    assert min_ielts == 6.0
    assert "Минимальный TOEFL: 75" in notes
    # Documents are kept separate from notes — restating the same admission
    # fact under two different labels is exactly the duplication this split
    # was introduced to avoid (see this function's own docstring).
    assert not any("IELTS" in n and "документ" in n.lower() for n in notes)
    assert required_documents == ["IELTS"]


async def test_import_majors_creates_programs_with_duration_and_ielts(db_session: AsyncSession):
    university = University(name="X", slug="x-univ", aliases=[], country="C", city="Y")
    db_session.add(university)
    await db_session.flush()

    institution = _institution(
        majors=[{"id": 1, "name": "Test Major", "durationYears": 4, "learningLanguage": "EN", "category": "ENGINEERING"}],
        enrollmentRequirements=[{"name": "Минимальный IELTS", "type": "LANGUAGE", "value": "6.0"}],
    )
    created, skipped = await _import_majors(db_session, university=university, institution=institution)
    assert created == 1
    assert skipped == 0

    result = await db_session.execute(select(Program).where(Program.university_id == university.id))
    program = result.scalar_one()
    assert program.name == "Test Major"
    assert program.source_category == "ENGINEERING"
    assert program.requirements["duration_years"] == 4
    assert program.requirements["min_ielts"] == 6.0
    assert program.cost_per_year is None


async def test_import_majors_skips_duplicate_name_without_aborting_batch(db_session: AsyncSession):
    university = University(name="X", slug="x-univ-2", aliases=[], country="C", city="Y")
    db_session.add(university)
    await db_session.flush()

    institution = _institution(
        majors=[
            {"id": 1, "name": "Same Name", "durationYears": 4, "learningLanguage": "EN", "category": "LAW"},
            {"id": 2, "name": "Same Name", "durationYears": 3, "learningLanguage": "RU", "category": "LAW"},
            {"id": 3, "name": "Different Name", "durationYears": 4, "learningLanguage": "EN", "category": "LAW"},
        ],
    )
    created, skipped = await _import_majors(db_session, university=university, institution=institution)
    assert created == 2  # "Same Name" once, "Different Name" once
    assert skipped == 1  # second "Same Name" collides on (university_id, name_normalized)
