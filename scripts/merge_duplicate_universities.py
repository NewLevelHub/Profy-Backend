"""One-off: merges University rows that are the same real institution
duplicated under two different slugs — found the first instance via
apply_university_enrichment_2027.py crashing on a unique-`ror_id` conflict
("HEC Paris" seeded twice: `hec-paris` and `hec-paris-finance`, the latter
apparently meant to be a specific program/campus but created as its own
University row instead of a Program under the main one). `ror_id` is the
canonical dedup key for universities (see University.ror_id's docstring /
docs/university-module-fix-plan.md B1), but duplicates predating a `ror_id`
assignment only share an exact `name` — so duplicates are found by exact
`University.name` match, not by ror_id (which is what the *enrichment*
script's own crash exposed here).

For each pair: keeps the row with more populated enrichment fields (see
`_ENRICHMENT_FIELDS`), re-points every `Program.university_id` that pointed
at the other row onto the keeper, merges in any field the other row has
that the keeper lacks, then deletes the other row. Any resulting duplicate
Program rows on the keeper (same specialty now listed twice) are left for
merge_duplicate_programs.py, which already handles that case and should run
after this script.

Idempotent: once a pair is merged, the exact-name query returns only one
row for it, so re-running is a no-op.

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/merge_duplicate_universities.py [--dry-run]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university import University

_ENRICHMENT_FIELDS = (
    "ror_id",
    "ovpo_code",
    "slug",
    "short_name",
    "location",
    "website",
    "ranking",
    "ranking_label",
    "uniranks_kz_rank",
    "uniranks_world_rank",
    "uniranks_note",
    "description",
    "source_url",
)


def _richness(u: University) -> int:
    score = sum(1 for f in _ENRICHMENT_FIELDS if getattr(u, f))
    score += len(u.aliases or [])
    score += len(u.contacts or {})
    score += len(u.facilities or {})
    score += len(u.fact_sources or {})
    return score


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        result = await db.execute(select(University))
        universities = result.scalars().all()

        groups: dict[str, list[University]] = {}
        for u in universities:
            groups.setdefault(u.name, []).append(u)

        merged = 0
        for name, group in groups.items():
            if len(group) < 2:
                continue

            # `slug` is the join key most of the seed pipeline filters
            # University by (apply_*.py scripts do `where(University.slug ==
            # slug)`) — a shorter slug within a duplicate-name group is a
            # strong signal of being the canonical entry vs. a "<slug>-<extra
            # word>" row created by mistake for what should have been a
            # Program, not a University (this is exactly the HEC Paris case
            # this script was written for: `hec-paris` vs
            # `hec-paris-finance`). Prefer it over raw field-count richness,
            # since surviving under the wrong slug would silently break
            # future enrichment lookups keyed on the canonical slug.
            group.sort(key=lambda u: (len(u.slug or u.name), -_richness(u), u.created_at))
            keeper, *rest = group

            for other in rest:
                print(f"[merge] keep {keeper.id} (slug={keeper.slug!r}) <- drop {other.id} (slug={other.slug!r}) name={name!r}")
                if dry_run:
                    continue

                # Reassign through the `university` relationship attribute,
                # not the raw `university_id` column — University.programs is
                # `lazy="selectin"` and already loaded, so touching the FK
                # column directly leaves that in-memory collection stale;
                # back_populates only stays consistent (both other.programs
                # shrinking and keeper.programs growing) when you go through
                # the relationship itself. Otherwise the unit-of-work still
                # treats these as other's children on flush and nulls their
                # (NOT NULL) university_id when other is deleted.
                for program in list(other.programs):
                    program.university = keeper
                await db.flush()

                # Capture what we need from `other` before deleting it — its
                # Python attributes stay readable after db.delete() until the
                # flush actually happens, but we flush the delete itself
                # first (see below) to free up other's unique columns
                # (ror_id/ovpo_code/slug) before assigning them to keeper.
                merge_fields = {f: getattr(other, f) for f in _ENRICHMENT_FIELDS}
                merge_aliases = list(other.aliases or [])
                merge_contacts = dict(other.contacts or {})
                merge_facilities = dict(other.facilities or {})
                merge_sources = dict(other.fact_sources or {})

                await db.delete(other)
                await db.flush()

                for field, value in merge_fields.items():
                    if not getattr(keeper, field) and value:
                        setattr(keeper, field, value)

                keeper.aliases = list({*(keeper.aliases or []), *merge_aliases})

                keeper_contacts = dict(keeper.contacts or {})
                for k, v in merge_contacts.items():
                    keeper_contacts.setdefault(k, v)
                keeper.contacts = keeper_contacts

                keeper_facilities = dict(keeper.facilities or {})
                for k, v in merge_facilities.items():
                    keeper_facilities.setdefault(k, v)
                keeper.facilities = keeper_facilities

                keeper_sources = dict(keeper.fact_sources or {})
                for k, v in merge_sources.items():
                    keeper_sources.setdefault(k, v)
                keeper.fact_sources = keeper_sources

                await db.flush()
                merged += 1

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}pairs merged: {merged}")


if __name__ == "__main__":
    asyncio.run(main())
