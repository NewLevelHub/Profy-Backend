"""Cross-database-stable resolution of University/Program rows for one-off
data scripts (scripts/apply_*.py, scripts/backfill_*.py) that read row
references out of a checked-in review/data file.

Why this exists
---------------
`University.id` and `Program.id` are `uuid.uuid4()` primary keys, generated
independently per row per database (`app/models/university.py`,
`app/models/program.py`). The same real university gets a *different* UUID
on every separately-seeded database — a developer's local copy, the dev
stack, prod on its first run of the jinaq pipeline. So a review file that
hardcodes `University.id` values snapshotted from whatever DB it was
generated against does not resolve on any other database: the apply script
silently matches nothing and reports "not found" / "already done" for every
entry (confirmed for `apply_uniranks_world_rank.py` and
`apply_foreign_university_dedup.py` — see PRO-244).

The durable keys that DO survive a re-seed, in the order this module tries
them:

1. ``jinaq_external_id`` — jinaq's own source-system institution id, written
   into ``university_external_refs`` (``source="jinaq"``) by
   ``import_jinaq_universities.py`` on every import regardless of which
   database it runs against. The reference pattern is
   ``apply_kz_university_merge.py``'s ``_resolve_jinaq_university`` (this
   module hoists it out so every script shares one implementation).
2. ``slug`` — ``University.slug`` is unique, indexed, and the de-facto stable
   key for curated rows; ~10 existing scripts already resolve by it.
3. ``ror_id`` — ``University.ror_id`` (Research Organization Registry) is the
   canonical dedup key for foreign universities, but sparsely populated, so
   it only helps the minority of rows that carry one.

``University.id`` / ``Program.id`` are deliberately NOT accepted as a lookup
key here — see the module docstring's first paragraph.

``Program`` has no ``slug``; it is resolved by its parent University plus its
degree-suffix-normalized name, which backs the
``(university_id, name_normalized)`` unique constraint
(``app/models/program.py``). ``normalize`` is re-exported from
``scripts.merge_duplicate_programs`` so callers building a review file and
callers consuming it use the exact same rule.
"""
import uuid

from sqlalchemy import select

from app.models.program import Program
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from scripts.merge_duplicate_programs import normalize

__all__ = [
    "resolve_jinaq_university",
    "resolve_university",
    "resolve_program",
    "repoint_jinaq_ref",
    "portable_keys",
    "normalize",
]

JINAQ_SOURCE = "jinaq"

# Field names a review/data record may use to carry a portable key. Kept in
# one place so the guardrail test (tests/unit/test_review_files_portable_keys.py)
# and the apply scripts agree on what counts as "portable".
_PORTABLE_KEY_FIELDS = (
    "jinaq_external_id",
    "external_id",
    "slug",
    "university_slug",
    "keep_slug",
    "remove_slug",
    "ror_id",
    "keep_ror_id",
    "remove_ror_id",
)


async def resolve_jinaq_university(db, external_id: str) -> University | None:
    """The current University row for a jinaq source id, via
    ``university_external_refs`` — the only key stable across database
    instances. Mirrors ``apply_kz_university_merge.py._resolve_jinaq_university``.
    """
    if external_id is None:
        return None
    ref = (
        await db.execute(
            select(UniversityExternalRef).where(
                UniversityExternalRef.source == JINAQ_SOURCE,
                UniversityExternalRef.external_id == str(external_id),
            )
        )
    ).scalar_one_or_none()
    if ref is None:
        return None
    return await db.get(University, ref.university_id)


async def resolve_university(
    db,
    *,
    jinaq_external_id: str | None = None,
    slug: str | None = None,
    ror_id: str | None = None,
) -> tuple[University | None, str | None]:
    """Resolve a University by whichever portable keys are supplied, trying
    ``jinaq_external_id`` -> ``slug`` -> ``ror_id`` in that order.

    Returns ``(row, matched_by)`` where ``matched_by`` is the name of the key
    that hit (``"jinaq_external_id"`` / ``"slug"`` / ``"ror_id"``), or
    ``(None, None)`` if nothing resolved. Never queries ``University.id``.
    """
    if jinaq_external_id:
        university = await resolve_jinaq_university(db, jinaq_external_id)
        if university is not None:
            return university, "jinaq_external_id"

    if slug:
        university = (
            await db.execute(select(University).where(University.slug == slug))
        ).scalar_one_or_none()
        if university is not None:
            return university, "slug"

    if ror_id:
        university = (
            await db.execute(select(University).where(University.ror_id == ror_id))
        ).scalar_one_or_none()
        if university is not None:
            return university, "ror_id"

    return None, None


async def resolve_program(db, *, university: University, name: str) -> Program | None:
    """The Program row for ``name`` at ``university``, matched on the same
    degree-suffix normalization that backs the
    ``(university_id, name_normalized)`` unique constraint — so at most one
    row can match.
    """
    if university is None or name is None:
        return None
    return (
        await db.execute(
            select(Program).where(
                Program.university_id == university.id,
                Program.name_normalized == normalize(name),
            )
        )
    ).scalar_one_or_none()


async def repoint_jinaq_ref(db, external_id: str, target_university_id: uuid.UUID) -> None:
    """Point the jinaq external ref for ``external_id`` at
    ``target_university_id`` and mark it ``match_method="manual"`` — the
    post-merge step that lets a later run recognise "already merged" instead
    of re-resolving a stale id (see ``apply_kz_university_merge.py``).
    """
    ref = (
        await db.execute(
            select(UniversityExternalRef).where(
                UniversityExternalRef.source == JINAQ_SOURCE,
                UniversityExternalRef.external_id == str(external_id),
            )
        )
    ).scalar_one_or_none()
    if ref is not None:
        ref.university_id = target_university_id
        ref.match_method = "manual"


def portable_keys(record: dict) -> dict:
    """The subset of ``record`` that is a cross-DB-portable row reference
    (see ``_PORTABLE_KEY_FIELDS``), with empty/None values dropped. Used by
    apply scripts to decide how to resolve a row and by the guardrail test
    to decide whether a record is safe.
    """
    if not isinstance(record, dict):
        return {}
    return {
        field: record[field]
        for field in _PORTABLE_KEY_FIELDS
        if record.get(field) not in (None, "", [], {})
    }
