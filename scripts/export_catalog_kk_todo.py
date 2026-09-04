#!/usr/bin/env python
"""
KZ-504: Export untranslated university/program/direction descriptions for kk.

Generates batches of JSON records for manual Claude translation.
Reads from DB and checks against existing `scripts/data/catalog_descriptions_kk.json`.
"""

import json
import argparse
from pathlib import Path
from typing import Any
import sys
import os

# Ensure psycopg2 is available for sync DB access
try:
    import psycopg2
except ImportError:
    os.system("pip install -q psycopg2-binary")
    import psycopg2

from sqlalchemy import select, create_engine
from sqlalchemy.orm import sessionmaker

# Local imports — adjust path if running outside docker
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import University, Program, Direction, Base
from app.config import settings

# Create sync session for script use (not async like app.database.async_session)
db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
sync_engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=sync_engine)


def load_existing_kk_translations():
    """Load already-translated records from committed files."""
    translations = {}
    desc_file = Path(__file__).parent / "data" / "catalog_descriptions_kk.json"
    if desc_file.exists():
        data = json.loads(desc_file.read_text(encoding="utf-8"))
        for rec in data:
            key = (rec.get("kind"), rec.get("university_key"), rec.get("program_name"))
            translations[key] = True
    return translations


def export_universities(session, only_kz=False):
    """Export university descriptions that need translation."""
    records = []
    query = select(University).filter(University.description != "")
    if only_kz:
        query = query.filter(University.country == "Казахстан")

    for uni in session.execute(query).scalars():
        key = uni.slug or f"jinaq:{uni.jinaq_external_id}" or f"ror:{uni.ror_id}"
        record = {
            "id": f"{key}#description",
            "kind": "university",
            "university_key": key,
            "ru": uni.description,
        }
        records.append(record)
    return records


def export_programs(session, only_kz=False):
    """Export program descriptions that need translation."""
    records = []
    uni_filter = ""
    if only_kz:
        uni_filter = " AND universities.country = 'Казахстан'"

    query = select(Program, University).join(University)
    if only_kz:
        query = query.filter(University.country == "Казахстан")

    for prog, uni in session.execute(query).all():
        if not prog.description and not prog.who_its_for:
            continue
        uni_key = uni.slug or f"jinaq:{uni.jinaq_external_id}" or f"ror:{uni.ror_id}"

        if prog.description:
            records.append({
                "id": f"{uni_key}#{prog.name}#description",
                "kind": "program",
                "university_key": uni_key,
                "program_name": prog.name,
                "ru": prog.description,
            })
        if prog.who_its_for:
            records.append({
                "id": f"{uni_key}#{prog.name}#who_its_for",
                "kind": "program",
                "university_key": uni_key,
                "program_name": prog.name,
                "field": "who_its_for",
                "ru": prog.who_its_for,
            })
    return records


def export_directions():
    """Export direction descriptions that need translation."""
    records = []
    ru_file = Path(__file__).parent / "direction_content_review.json"
    kk_file = Path(__file__).parent / "direction_content_review_kk.json"

    if not ru_file.exists():
        return records

    review_data = json.loads(ru_file.read_text(encoding="utf-8"))

    # Already-translated kk values, keyed by (slug, field-or-'description', idx)
    done: dict = {}
    if kk_file.exists():
        for d in json.loads(kk_file.read_text(encoding="utf-8")):
            done[(d["slug"], "description", 0)] = d.get("description")
            for f in ("skills_needed", "subjects_to_develop", "first_steps"):
                for i, v in enumerate(d.get(f, []) or []):
                    done[(d["slug"], f, i)] = v
    ru_by_slug = {}
    if kk_file.exists():
        for d in json.loads(ru_file.read_text(encoding="utf-8")):
            ru_by_slug[d["slug"]] = d

    def _needs(slug, field, idx, ru_val):
        """True when kk value is missing or still equals the ru source string."""
        cur = done.get((slug, field, idx))
        return not cur or cur == ru_val

    for direction in review_data:
        slug = direction["slug"]
        name = direction["name"]

        # Description
        _desc = direction.get("description") or ""
        if _desc and not _desc.startswith("_bootstrap") and _needs(slug, "description", 0, _desc):
            records.append({
                "id": f"{slug}#description",
                "kind": "direction",
                "slug": slug,
                "ru": _desc,
            })

        # Skills, subjects, first steps
        for field in ["skills_needed", "subjects_to_develop", "first_steps"]:
            if field in direction and direction[field]:
                for idx, item in enumerate(direction[field]):
                    if not _needs(slug, field, idx, item):
                        continue
                    records.append({
                        "id": f"{slug}#{field}#{idx}",
                        "kind": "direction",
                        "slug": slug,
                        "field": field,
                        "_index": idx,
                        "ru": item,
                    })
    return records


def write_batches(records, batch_size=30, output_dir="scripts/data/kk_todo"):
    """Write records to batches."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        batch_file = Path(output_dir) / f"batch_{i//batch_size:03d}.json"
        batch_file.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {len(batch)} records to {batch_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", default="all", choices=["university", "program", "direction", "all"])
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-kz", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    records = []
    session = SessionLocal()

    try:
        if args.kind in ("university", "all"):
            print("Exporting universities...")
            records.extend(export_universities(session, only_kz=args.only_kz))

        if args.kind in ("program", "all"):
            print("Exporting programs...")
            records.extend(export_programs(session, only_kz=args.only_kz))

        if args.kind in ("direction", "all"):
            print("Exporting directions...")
            records.extend(export_directions())

        if args.limit:
            records = records[:args.limit]

        if args.report:
            print(f"\nTotal records to translate: {len(records)}")

        write_batches(records, batch_size=args.batch_size)

    finally:
        session.close()


if __name__ == "__main__":
    main()
