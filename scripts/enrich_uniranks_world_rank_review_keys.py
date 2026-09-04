"""One-time: backfills cross-DB-portable keys (`slug`, `ror_id`,
`jinaq_external_id`) into the *existing* scripts/data/uniranks_world_rank_review.json
so apply_uniranks_world_rank.py can resolve rows on a database other than
the one the file was generated against (PRO-245 — see
docs/content-pipeline-id-resolution-audit.md).

Does NOT re-crawl uniranks.com — the `world_rank` values in the file stay
untouched. It only needs a database to look up the current `slug` /
`ror_id` / jinaq ref for each row.

Two resolution modes, auto-detected (override with --force-id-match /
--force-name-match):

  id-match   Run this against the SAME database the review file was
             generated on: each record's `university_id` still resolves, and
             its keys are read straight off that row. Exact.

  name-match Fallback for any other database: match each record to a row by
             exact normalized (our_name, country, city) — the generator
             copied those three fields verbatim from University.name/country/
             city, so exact normalized equality is the right join. A record
             that matches zero or >1 rows is marked `"needs_review": true`
             with an `"_unresolved_reason"`; its keys are left null for a
             human to fill.

Run --report-only first to see the resolved / needs_review split and the
ambiguous tuples before writing anything.

Run inside the api container:
  docker-compose exec api python scripts/enrich_uniranks_world_rank_review_keys.py [--report-only] [--force-id-match|--force-name-match]
"""
import argparse
import asyncio
import json
import os
import sys
import uuid
from collections import defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from scripts.import_jinaq_universities import _normalize

DATA_PATH = os.path.join(_ROOT, "scripts", "data", "uniranks_world_rank_review.json")

_PORTABLE = ("slug", "ror_id", "jinaq_external_id")
_ID_MODE_THRESHOLD = 0.95


def _inject(record: dict, university: University, jinaq_ext_by_uni_id: dict) -> None:
    """Fill any portable key that is missing/None on the record. Never
    overwrites a value that is already there."""
    values = {
        "slug": university.slug,
        "ror_id": university.ror_id,
        "jinaq_external_id": jinaq_ext_by_uni_id.get(university.id),
    }
    for key in _PORTABLE:
        if not record.get(key) and values[key] is not None:
            record[key] = values[key]
    record.pop("needs_review", None)
    record.pop("_unresolved_reason", None)


async def _load_indexes(db):
    universities = (await db.execute(select(University))).scalars().all()
    by_id = {u.id: u for u in universities}

    by_name_key: dict[tuple, list[University]] = defaultdict(list)
    for u in universities:
        by_name_key[(_normalize(u.name), _normalize(u.country), _normalize(u.city))].append(u)

    refs = await db.execute(
        select(UniversityExternalRef.university_id, UniversityExternalRef.external_id).where(
            UniversityExternalRef.source == "jinaq"
        )
    )
    jinaq_ext_by_uni_id = {uni_id: ext_id for uni_id, ext_id in refs.all()}
    return by_id, by_name_key, jinaq_ext_by_uni_id


def _id_resolution_rate(records: list[dict], by_id: dict) -> float:
    if not records:
        return 0.0
    resolved = 0
    for r in records:
        raw = r.get("university_id")
        try:
            if raw and uuid.UUID(str(raw)) in by_id:
                resolved += 1
        except (ValueError, TypeError):
            pass
    return resolved / len(records)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true", help="print the resolution split, write nothing")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--force-id-match", action="store_true")
    group.add_argument("--force-name-match", action="store_true")
    args = parser.parse_args()

    with open(DATA_PATH, encoding="utf-8") as f:
        records = json.load(f)

    async with async_session() as db:
        by_id, by_name_key, jinaq_ext_by_uni_id = await _load_indexes(db)

    rate = _id_resolution_rate(records, by_id)
    if args.force_id_match:
        mode = "id-match"
    elif args.force_name_match:
        mode = "name-match"
    else:
        mode = "id-match" if rate >= _ID_MODE_THRESHOLD else "name-match"
    print(f"{len(records)} records; university_id resolves for {rate:.1%} on this DB -> mode: {mode}")

    resolved = 0
    needs_review = 0
    ambiguous: list[tuple] = []

    for record in records:
        university = None

        if mode == "id-match":
            raw = record.get("university_id")
            try:
                university = by_id.get(uuid.UUID(str(raw))) if raw else None
            except (ValueError, TypeError):
                university = None
        else:
            key = (
                _normalize(record.get("our_name")),
                _normalize(record.get("country")),
                _normalize(record.get("city")),
            )
            matches = by_name_key.get(key, [])
            if len(matches) == 1:
                university = matches[0]
            elif len(matches) > 1:
                ambiguous.append(key)

        if university is None:
            needs_review += 1
            if not args.report_only:
                record["needs_review"] = True
                record["_unresolved_reason"] = (
                    "university_id not on this DB" if mode == "id-match"
                    else f"{'no' if not by_name_key.get(key) else 'multiple'} (name, country, city) match"
                )
            continue

        resolved += 1
        if not args.report_only:
            _inject(record, university, jinaq_ext_by_uni_id)

    with_portable = sum(1 for r in records if any(r.get(k) for k in _PORTABLE))
    print(f"resolved: {resolved}, needs_review: {needs_review}, records carrying a portable key: {with_portable}/{len(records)}")
    if ambiguous:
        print(f"\n{len(ambiguous)} ambiguous (name, country, city) tuples (routed to needs_review):")
        for key in ambiguous[:40]:
            print(f"  {key}")

    if args.report_only:
        print("\n[report-only] nothing written")
        return

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\nrewrote {DATA_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
