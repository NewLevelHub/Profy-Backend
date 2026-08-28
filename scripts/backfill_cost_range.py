"""One-time backfill for Program.cost_per_year_min/max/cost_currency (A6).

Two sources, never in conflict since they're mutually exclusive per row:
  - `cost_per_year` already set (exact KZT figure, all Kazakhstani programs)
    -> min=max=cost_per_year, currency=KZT. No parsing involved.
  - `cost_label` free text (everything else) -> scripts/parse_cost_label.py,
    which only returns a value when the text states exactly one unambiguous
    annual figure — see that module's docstring for why roughly a third of
    labels are deliberately left unparsed rather than guessed at.

Idempotent: only touches rows where cost_per_year_min IS NULL.

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/backfill_cost_range.py [--dry-run]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from scripts.parse_cost_label import parse_cost_label


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        result = await db.execute(select(Program).where(Program.cost_per_year_min.is_(None)))
        programs = result.scalars().all()

        from_exact = from_label = skipped = 0
        for p in programs:
            if p.cost_per_year is not None:
                lo = hi = p.cost_per_year
                currency = "KZT"
                from_exact += 1
            elif p.cost_label:
                parsed = parse_cost_label(p.cost_label)
                if parsed is None:
                    skipped += 1
                    continue
                lo, hi, currency = parsed
                from_label += 1
            else:
                skipped += 1
                continue

            if not dry_run:
                p.cost_per_year_min = lo
                p.cost_per_year_max = hi
                p.cost_currency = currency

        if not dry_run:
            await db.commit()

        print(
            f"{'DRY RUN — ' if dry_run else ''}"
            f"from exact cost_per_year: {from_exact}, from parsed cost_label: {from_label}, "
            f"skipped (no source or ambiguous text): {skipped}"
        )


if __name__ == "__main__":
    asyncio.run(main())
