#!/usr/bin/env python
"""
KZ-504: Apply Kazakh translations from Claude into committed files and DB.

Reads from `scripts/data/kk_done/` batches, validates Kazakh, merges into
`catalog_descriptions_kk.json` and `direction_content_review_kk.json`.
"""

import json
import argparse
import re
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

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import University, Program
from app.config import settings
from scripts.entity_resolver import resolve_university, resolve_program

# Create sync session for script use (not async like app.database.async_session)
db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
sync_engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=sync_engine)

# Kazakh special characters that distinguish it from Russian
KK_CHARS = set("әғқңөұүһі")
# Common Latin tokens that should be preserved
LATIN_TOKENS = {"IELTS", "TOEFL", "SAT", "Data", "Engineer", "Science", "Nazarbayev", "University"}


def is_kazakh_text(text: str, min_kk_chars_per_words=0.25) -> bool:
    """Check if text is likely Kazakh (not Russian or machine error)."""
    if not text or len(text) < 4:
        return True  # Very short text passes

    words = text.split()
    if len(words) < 1:
        return False

    # Count words with at least one Kazakh-specific character
    kk_word_count = 0
    for word in words:
        # Skip pure-Latin tokens
        if word in LATIN_TOKENS or all(c.isalpha() and c.isascii() for c in word):
            continue
        if any(c in KK_CHARS for c in word):
            kk_word_count += 1

    # At least min_kk_chars_per_words of non-Latin words should have KK chars
    latin_skipped = sum(1 for w in words if w in LATIN_TOKENS or all(c.isalpha() and c.isascii() for c in w))
    non_latin_words = len(words) - latin_skipped
    if non_latin_words > 0:
        return kk_word_count / non_latin_words >= min_kk_chars_per_words
    return True


def load_batch_files(input_dir: str) -> list:
    """Load all batch files from directory."""
    records = []
    input_path = Path(input_dir)
    if not input_path.exists():
        return records

    for batch_file in sorted(input_path.glob("batch_*.json")):
        batch = json.loads(batch_file.read_text(encoding="utf-8"))
        records.extend(batch)
    return records


def validate_and_report(records: list) -> tuple:
    """Validate Kazakh content, return (valid_records, invalid_records)."""
    valid = []
    invalid = []

    for rec in records:
        kk_text = rec.get("kk", "")
        if not is_kazakh_text(kk_text):
            rec["_issue"] = "LANGUAGE_MISMATCH"
            invalid.append(rec)
        else:
            valid.append(rec)

    return valid, invalid


def merge_university_descriptions(records: list, file_path: str):
    """Merge university/program translations into committed file."""
    existing = {}
    if Path(file_path).exists():
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        for rec in data:
            key = (rec["kind"], rec.get("university_key"), rec.get("program_name"))
            existing[key] = rec

    # Add new translations
    for rec in records:
        if rec["kind"] == "university":
            key = ("university", rec["university_key"], None)
        else:  # program
            key = ("program", rec["university_key"], rec["program_name"])
        existing[key] = rec

    # Write back
    output = list(existing.values())
    Path(file_path).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_direction_descriptions(records: list, file_path: str):
    """Merge direction translations into committed review file."""
    existing = {}
    if Path(file_path).exists():
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        for rec in data:
            existing[rec["slug"]] = rec

    # Apply translations by slug
    for rec in records:
        if rec["kind"] != "direction":
            continue
        slug = rec["slug"]
        if slug not in existing:
            continue

        if "field" not in rec:
            # Description
            existing[slug]["description"] = rec["kk"]
        else:
            # List field (skills_needed, etc.)
            field = rec["field"]
            if field not in existing[slug]:
                existing[slug][field] = []
            # Assume we're adding in order; pad if needed
            idx = rec.get("_index", 0)
            while len(existing[slug][field]) <= idx:
                existing[slug][field].append("")
            existing[slug][field][idx] = rec["kk"]

    # Write back
    output = list(existing.values())
    Path(file_path).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_to_db(records: list, session):
    """Apply translations to database via entity_resolver."""
    for rec in records:
        if rec["kind"] == "university":
            uni = resolve_university(session, rec["university_key"])
            if uni and not uni.description_i18n:
                uni.description_i18n = {}
            if uni:
                uni.description_i18n["kk"] = rec["kk"]
                session.add(uni)

        elif rec["kind"] == "program":
            prog = resolve_program(
                session,
                rec["university_key"],
                rec["program_name"]
            )
            if prog:
                if not prog.description_i18n:
                    prog.description_i18n = {}
                field = rec.get("field", "description")
                if field == "description":
                    prog.description_i18n["kk"] = rec["kk"]
                elif field == "who_its_for":
                    if not prog.who_its_for_i18n:
                        prog.who_its_for_i18n = {}
                    prog.who_its_for_i18n["kk"] = rec["kk"]
                session.add(prog)

    session.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_dir", default="scripts/data/kk_done")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--to-db", action="store_true")
    parser.add_argument("--report", type=str)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Load batch files
    print(f"Loading from {args.from_dir}...")
    records = load_batch_files(args.from_dir)
    print(f"Loaded {len(records)} records")

    # Validate
    valid, invalid = validate_and_report(records)
    print(f"Valid: {len(valid)}, Invalid: {len(invalid)}")

    if invalid and args.report:
        Path(args.report).write_text(
            json.dumps(invalid, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"Invalid records written to {args.report}")

    if args.dry_run:
        print("Dry run: no changes made")
        return

    # Merge into committed files
    desc_file = Path(__file__).parent / "data" / "catalog_descriptions_kk.json"
    dir_file = Path(__file__).parent / "direction_content_review_kk.json"

    uni_prog_records = [r for r in valid if r["kind"] in ("university", "program")]
    if uni_prog_records:
        merge_university_descriptions(uni_prog_records, str(desc_file))
        print(f"Merged {len(uni_prog_records)} university/program records into {desc_file}")

    dir_records = [r for r in valid if r["kind"] == "direction"]
    if dir_records:
        merge_direction_descriptions(dir_records, str(dir_file))
        print(f"Merged {len(dir_records)} direction records into {dir_file}")

    # Apply to DB
    if args.to_db:
        session = SessionLocal()
        try:
            apply_to_db(valid, session)
            print(f"Applied {len(valid)} translations to database")
        finally:
            session.close()


if __name__ == "__main__":
    main()
