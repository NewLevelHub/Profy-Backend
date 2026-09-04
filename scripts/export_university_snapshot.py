"""
Read-only export: dump the current `universities` / `programs` /
`program_directions` state into ONE portable JSON file.

This is step 1 of collapsing the ~30-script university pipeline into a single
committed snapshot + one loader. This script ONLY reads the DB and writes a
file — it never writes to the database, deletes anything, or touches the
other scripts.

What goes in the file:
  - every `universities` row (minus the per-DB random `id` and `created_at`)
  - its `university_external_refs` (jinaq / wikidata source ids)
  - every `programs` row of that university (minus `id`, `university_id`,
    the DB-computed `name_normalized`, and `created_at`), with its
    profession tags flattened to a sorted list of `Direction.slug`

What is deliberately left out:
  - `id` / `university_id` — a per-database `uuid4()` (see PRO-244). Rows are
    identified in the file by portable keys instead: jinaq external id, slug,
    ror_id, ovpo_code, plus name/city/country.
  - users, assessments, roadmaps, `university_images` (photos live in a
    slug-keyed folder, not the DB) — not part of "what makes the catalogue".

Output is sorted (universities by country+name+slug, programs by name,
refs by source+id) so the file diffs cleanly in git.

Run inside the api container (nothing is committed to the DB):
  docker compose exec api python scripts/export_university_snapshot.py [--out PATH] [--indent N]
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef

DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "university_snapshot.json"
)

# Per-DB / derived columns that must NOT be snapshotted — see module docstring.
SKIP_UNIVERSITY_COLS = {"id", "created_at"}
SKIP_PROGRAM_COLS = {"id", "university_id", "name_normalized", "created_at"}


def _ser(value):
    """JSON-safe form of a single column value."""
    if isinstance(value, Decimal):
        # str, not float — keep exact currency amounts, let the loader do Decimal(...)
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _row_dict(obj, skip: set[str]) -> dict:
    """Every mapped column of `obj` except `skip`, JSON-serialised, in the
    model's column order."""
    return {
        col.name: _ser(getattr(obj, col.name))
        for col in obj.__table__.columns
        if col.name not in skip
    }


def _portable_keys(u: University, jinaq_external_id: str | None) -> dict:
    """The cross-DB-stable identifiers for a university row, empty values
    dropped. The loader resolves rows through these, never through `id`."""
    keys = {
        "jinaq_id": jinaq_external_id,
        "slug": u.slug,
        "ror_id": u.ror_id,
        "ovpo_code": u.ovpo_code,
    }
    return {k: v for k, v in keys.items() if v not in (None, "")}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT, help=f"output path (default: {DEFAULT_OUT})")
    parser.add_argument("--indent", type=int, default=2, help="JSON indent; 0 = compact (default: 2)")
    args = parser.parse_args()

    async with async_session() as db:
        refs_by_uni: dict[UUID, list[UniversityExternalRef]] = {}
        for ref in (await db.execute(select(UniversityExternalRef))).scalars().all():
            refs_by_uni.setdefault(ref.university_id, []).append(ref)

        universities = (
            (
                await db.execute(
                    select(University).options(
                        selectinload(University.programs).selectinload(Program.directions)
                    )
                )
            )
            .scalars()
            .all()
        )

        uni_records: list[dict] = []
        total_programs = 0
        tagged_programs = 0

        for u in universities:
            refs = sorted(
                refs_by_uni.get(u.id, []),
                key=lambda r: (r.source or "", r.external_id or ""),
            )
            jinaq_external_id = next(
                (r.external_id for r in refs if r.source == "jinaq"), None
            )

            programs = []
            for p in sorted(u.programs, key=lambda p: (p.name or "")):
                total_programs += 1
                professions = sorted(d.slug for d in p.directions)
                if professions:
                    tagged_programs += 1
                programs.append(
                    {
                        **_row_dict(p, SKIP_PROGRAM_COLS),
                        "professions": professions,
                    }
                )

            uni_records.append(
                {
                    "keys": _portable_keys(u, jinaq_external_id),
                    **_row_dict(u, SKIP_UNIVERSITY_COLS),
                    "external_refs": [
                        {
                            "source": r.source,
                            "external_id": r.external_id,
                            "external_name": r.external_name,
                            "match_method": r.match_method,
                        }
                        for r in refs
                    ],
                    "programs": programs,
                }
            )

    uni_records.sort(
        key=lambda r: (r.get("country") or "", r.get("name") or "", r.get("slug") or "")
    )

    total_refs = sum(len(r["external_refs"]) for r in uni_records)
    payload = {
        "_meta": {
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "source": "local DB snapshot via scripts/export_university_snapshot.py",
            "note": (
                "Portable snapshot of universities/programs/program_directions. "
                "Rows are keyed by jinaq_id/slug/ror_id/ovpo_code, never by the "
                "per-DB `id`. Photos, users and assessments are not included."
            ),
            "counts": {
                "universities": len(uni_records),
                "programs": total_programs,
                "programs_with_profession_tag": tagged_programs,
                "external_refs": total_refs,
            },
        },
        "universities": uni_records,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=args.indent or None,
            separators=None if args.indent else (",", ":"),
        )
        f.write("\n")

    size_mb = os.path.getsize(args.out) / (1024 * 1024)
    print(f"Wrote {args.out}  ({size_mb:.1f} MB)")
    print(
        f"  universities: {len(uni_records)}\n"
        f"  programs: {total_programs}  (with >=1 profession tag: {tagged_programs}, "
        f"{tagged_programs * 100 // total_programs if total_programs else 0}%)\n"
        f"  external_refs: {total_refs}"
    )


if __name__ == "__main__":
    asyncio.run(main())
