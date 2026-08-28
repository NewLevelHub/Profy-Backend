"""Generates scripts/data/jinaq/specialty_direction_review.json — a review
file for hand-mapping jinaq specialty names to Direction (profession) slugs,
same spirit as scripts/specialty_profession_map.py's SPECIALTY_TO_PROFESSIONS
for the original KZ dataset.

Deliberately does NOT propose any mapping itself, not even a draft one:
scripts/seed_kz_universities.py's own docstring documents that this team
already tried classifying specialties by category/group twice before and
both attempts produced "confidently wrong matches" — a shared category is
not the same thing as a real profession match. So this only prepares the
raw material (distinct specialty names, ranked by how many Program rows
they'd affect, with enough context to judge each one) for a human to fill
in `direction_slugs` by hand. Nothing here is applied to the DB — that's
scripts/apply_jinaq_specialty_directions.py (a separate script, to be
written once this review file has been filled in), which will look up
Program rows by name and attach the reviewed Direction slugs.

Keyed by distinct specialty NAME (1581 of them across all 10,113 majors),
not by row — matches every Program that shares that name, across every
university, in one entry. Sorted by frequency descending so reviewing the
top ~200-300 names first covers ~80-83% of all specialty rows; the long
tail (names appearing once or twice) can be left unmapped, same as the
existing "known deferred gap" for some KZ programs.

Run inside the api container:
  docker-compose exec api python scripts/generate_jinaq_specialty_direction_review.py [--top N]
"""
import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.direction import Direction

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jinaq", "universities.json")
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "jinaq", "specialty_direction_review.json"
)
DEFAULT_TOP_N = 300


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


async def main(*, top_n: int) -> None:
    with open(DATA_PATH, encoding="utf-8") as f:
        institutions: list[dict] = json.load(f)

    counts: Counter[str] = Counter()
    display_name: dict[str, str] = {}
    categories: dict[str, Counter] = defaultdict(Counter)
    universities: dict[str, list[str]] = defaultdict(list)

    for institution in institutions:
        uni_name = institution.get("name", "")
        for major in institution.get("majors") or []:
            raw_name = major.get("name") or ""
            if not raw_name:
                continue
            key = _normalize(raw_name)
            counts[key] += 1
            display_name.setdefault(key, raw_name)
            if major.get("category"):
                categories[key][major["category"]] += 1
            if uni_name and len(universities[key]) < 3 and uni_name not in universities[key]:
                universities[key].append(uni_name)

    ranked = counts.most_common(top_n)
    total_rows = sum(counts.values())
    covered_rows = sum(c for _, c in ranked)

    async with async_session() as db:
        directions = (await db.execute(select(Direction).order_by(Direction.slug))).scalars().all()

    output = {
        "_readme": (
            "Fill in `direction_slugs` for each entry below with slugs from "
            "`available_directions` — one specialty may prepare someone for "
            "several professions, or none if it doesn't clearly match any. "
            "Leave `direction_slugs: []` for anything you're not confident "
            "about; an empty list is a valid, honest answer, not a TODO. "
            "Do not guess from `sample_categories` alone — that's exactly "
            "the classification-by-category approach this project already "
            "tried and rejected (see this script's own docstring)."
        ),
        "available_directions": [
            {"slug": d.slug, "name": d.name, "holland_code": d.holland_code} for d in directions
        ],
        "specialties": [
            {
                "name": display_name[key],
                "count": count,
                "sample_categories": list(categories[key].keys()),
                "sample_universities": universities[key],
                "direction_slugs": [],
            }
            for key, count in ranked
        ],
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(ranked)} specialty names to {OUTPUT_PATH}")
    print(f"Covers {covered_rows}/{total_rows} major rows ({100 * covered_rows / total_rows:.1f}%)")
    print(f"{len(directions)} available direction slugs listed for reference")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    args = parser.parse_args()
    asyncio.run(main(top_n=args.top))
