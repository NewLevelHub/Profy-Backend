"""Exercises scripts/entity_resolver.py against a real, per-test rolled-back
DB session (see tests/conftest.py). Kept under integration/ (not unit/)
because it needs the DB — same placement as test_university_import_logic.py.
The pure-file-scan guardrail lives in tests/unit/test_review_files_portable_keys.py.

The local/CI database is really seeded (it carries live jinaq data), so
fixtures here use uuid-suffixed slugs and external ids to avoid colliding
with existing rows on the unique constraints.
"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.program import Program
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from scripts.entity_resolver import (
    portable_keys,
    repoint_jinaq_ref,
    resolve_jinaq_university,
    resolve_program,
    resolve_university,
)


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


async def _university(db: AsyncSession, **overrides: object) -> University:
    base = dict(
        name="Test University",
        slug=_uniq("test-university"),
        aliases=[],
        country="Testland",
        city="Testville",
    )
    base.update(overrides)
    university = University(**base)
    db.add(university)
    await db.flush()
    return university


async def _jinaq_ref(db: AsyncSession, *, external_id: str, university_id) -> UniversityExternalRef:
    ref = UniversityExternalRef(
        source="jinaq", external_id=external_id, university_id=university_id, match_method="new"
    )
    db.add(ref)
    await db.flush()
    return ref


async def test_resolve_jinaq_university_by_ref(db_session: AsyncSession):
    uni = await _university(db_session)
    ext = _uniq("ext")
    await _jinaq_ref(db_session, external_id=ext, university_id=uni.id)

    resolved = await resolve_jinaq_university(db_session, ext)
    assert resolved is not None and resolved.id == uni.id
    assert await resolve_jinaq_university(db_session, _uniq("missing")) is None


async def test_resolve_jinaq_university_coerces_non_str_external_id(db_session: AsyncSession):
    uni = await _university(db_session)
    await _jinaq_ref(db_session, external_id="88888001", university_id=uni.id)
    assert (await resolve_jinaq_university(db_session, 88888001)).id == uni.id


async def test_resolve_university_key_priority(db_session: AsyncSession):
    """jinaq_external_id wins even when the slug passed alongside points at a
    different row."""
    jinaq_uni = await _university(db_session, name="Jinaq Side")
    other_uni = await _university(db_session, name="Curated Side")
    ext = _uniq("ext")
    await _jinaq_ref(db_session, external_id=ext, university_id=jinaq_uni.id)

    row, matched_by = await resolve_university(
        db_session, jinaq_external_id=ext, slug=other_uni.slug
    )
    assert row.id == jinaq_uni.id
    assert matched_by == "jinaq_external_id"

    # Falls through to slug when the jinaq id doesn't resolve.
    row, matched_by = await resolve_university(
        db_session, jinaq_external_id=_uniq("nope"), slug=other_uni.slug
    )
    assert row.id == other_uni.id
    assert matched_by == "slug"


async def test_resolve_university_by_ror_id(db_session: AsyncSession):
    ror = f"https://ror.org/{uuid.uuid4().hex[:9]}"
    uni = await _university(db_session, ror_id=ror)
    row, matched_by = await resolve_university(db_session, ror_id=ror)
    assert row.id == uni.id
    assert matched_by == "ror_id"


async def test_resolve_university_no_match_returns_none_none(db_session: AsyncSession):
    row, matched_by = await resolve_university(
        db_session, slug=_uniq("does-not-exist"), ror_id=_uniq("nope")
    )
    assert row is None
    assert matched_by is None


async def test_resolve_program_respects_degree_suffix_normalization(db_session: AsyncSession):
    uni = await _university(db_session)
    program = Program(
        university_id=uni.id,
        name="Переводческое дело (бакалавр)",
        language="ru",
    )
    db_session.add(program)
    await db_session.flush()

    # Looked up by a name without the degree suffix — normalization collapses both.
    found = await resolve_program(db_session, university=uni, name="Переводческое дело")
    assert found is not None and found.id == program.id

    # A genuinely different specialization must not match.
    assert await resolve_program(db_session, university=uni, name="Международное право") is None


async def test_repoint_jinaq_ref(db_session: AsyncSession):
    old_uni = await _university(db_session)
    new_uni = await _university(db_session)
    ext = _uniq("ext")
    await _jinaq_ref(db_session, external_id=ext, university_id=old_uni.id)

    await repoint_jinaq_ref(db_session, ext, new_uni.id)
    await db_session.flush()

    resolved = await resolve_jinaq_university(db_session, ext)
    assert resolved.id == new_uni.id


def test_portable_keys_extracts_only_portable_fields():
    record = {
        "university_id": "d1f4-stale-uuid",
        "our_name": "Massachusetts Institute of Technology",
        "slug": "massachusetts-institute-of-technology",
        "jinaq_external_id": "44",
        "ror_id": None,
        "world_rank": 1,
    }
    assert portable_keys(record) == {
        "slug": "massachusetts-institute-of-technology",
        "jinaq_external_id": "44",
    }
    assert portable_keys({"university_id": "only-a-stale-uuid"}) == {}
    assert portable_keys("not a dict") == {}
