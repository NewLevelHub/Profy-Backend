"""One-off: merges Program rows that are the same real specialty duplicated
under two names at the same university — a bare name from the bulk KZ scrape
(seed_kz_universities.py) and a "<name> (бакалавр)"-suffixed name from the
older hand-picked legacy batch (see docs/ovpo-registry-gap-analysis.md /
the 16-program min_gpa investigation earlier in this project). Found by
normalizing away only degree-level suffixes ("(бакалавр)", "(магистратура)",
etc.) — NOT all parenthetical text, since many suffixes are real distinct
specializations (e.g. "Переводческое дело (восточные языки)" vs "(западные
языки)" are two different programs, confirmed by inspecting the data before
writing this script) and must never be treated as duplicates.

For each pair: keeps the row with richer `requirements` (more populated
keys — the legacy row almost always wins, since it usually carries
min_gpa/admission_scores_2026), merges in anything the other row has that
the keeper lacks (cost_per_year, cost_label, description, who_its_for,
requirements keys, deadlines keys, union of career_options/grants/directions),
then deletes the other row.

Idempotent: the normalized-name query returns nothing once a pair is merged,
so re-running is a no-op.

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/merge_duplicate_programs.py [--dry-run]
"""
import asyncio
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.program import Program

# Degree-level / track labels only — deliberately narrow. Broadening this to
# strip ALL parenthetical text would wrongly merge distinct specializations.
DEGREE_SUFFIX_RE = re.compile(
    r"\s*\((?:бакалавр(?:,\s*[^)]*)?|магистратура|практический психолог)\)\s*",
    re.IGNORECASE,
)


def normalize(name: str) -> str:
    return DEGREE_SUFFIX_RE.sub("", name).strip().lower()


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        result = await db.execute(select(Program).options(selectinload(Program.directions)))
        programs = result.scalars().all()

        groups: dict[tuple, list[Program]] = {}
        for p in programs:
            groups.setdefault((p.university_id, normalize(p.name)), []).append(p)

        merged = 0
        for (university_id, norm), group in groups.items():
            if len(group) < 2:
                continue

            group.sort(key=lambda p: len(p.requirements or {}), reverse=True)
            keeper, *rest = group

            for other in rest:
                print(f"[merge] keep {keeper.id} {keeper.name!r} <- drop {other.id} {other.name!r} (university {university_id})")
                if dry_run:
                    continue

                if keeper.cost_per_year is None and other.cost_per_year is not None:
                    keeper.cost_per_year = other.cost_per_year
                if keeper.cost_label is None and other.cost_label:
                    keeper.cost_label = other.cost_label
                if keeper.description is None and other.description:
                    keeper.description = other.description
                if keeper.who_its_for is None and other.who_its_for:
                    keeper.who_its_for = other.who_its_for

                keeper_req = dict(keeper.requirements or {})
                for k, v in (other.requirements or {}).items():
                    keeper_req.setdefault(k, v)
                keeper.requirements = keeper_req

                keeper_dl = dict(keeper.deadlines or {})
                for k, v in (other.deadlines or {}).items():
                    keeper_dl.setdefault(k, v)
                keeper.deadlines = keeper_dl

                keeper.career_options = list({*(keeper.career_options or []), *(other.career_options or [])})
                keeper.grants = (keeper.grants or []) + [
                    g for g in (other.grants or []) if g not in (keeper.grants or [])
                ]
                keeper.directions = list({*keeper.directions, *other.directions})

                await db.flush()
                await db.execute(delete(Program).where(Program.id == other.id))
                merged += 1

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}pairs merged: {merged}")


if __name__ == "__main__":
    asyncio.run(main())
