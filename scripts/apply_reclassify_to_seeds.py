"""
OFFLINE developer tool — mirrors the direction_slugs retagging already
applied to the database (via reclassify_program_directions.py --apply) back
onto the seed script literals, so the seed files stay the source of truth
and the change is a normal, reviewable git diff.

Deterministic: reuses the exact same match_specialties() function, so a
program's new tag is a pure function of its "name" field — no DB lookup
needed, and the result is guaranteed to match what's already in the DB.

Only rewrites a "direction_slugs": [...] literal when its CURRENT value is
entirely section-level slugs (e.g. ["akinator-medicine"]) — a program
already carrying a specific leaf slug is left untouched (it was already
precise, whether hand-curated or previously tagged).

Usage (inside Docker):
    docker-compose exec api python scripts/apply_reclassify_to_seeds.py            # dry run, prints a diff-style summary
    docker-compose exec api python scripts/apply_reclassify_to_seeds.py --apply    # rewrites the files in place
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.reclassify_program_directions import match_specialties  # noqa: E402

SEED_FILES = [
    "scripts/seed_universities.py",
    "scripts/seed_astana_universities.py",
    "scripts/seed_almaty_universities.py",
]

_NAME_RE = re.compile(r'^\s*"name":\s*"(?P<name>(?:[^"\\]|\\.)*)",\s*$')
_SLUGS_RE = re.compile(r'^(?P<indent>\s*)"direction_slugs":\s*\[(?P<items>.*?)\],\s*$')


def _parse_items(items: str) -> list[str]:
    return [s.strip().strip('"') for s in items.split(",") if s.strip()]


def _render(slugs: list[str]) -> str:
    return "[" + ", ".join(f'"{s}"' for s in slugs) + "]"


def process_file(path: str, apply: bool) -> tuple[int, int]:
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    current_name: str | None = None
    changed = 0
    unchanged = 0

    for i, line in enumerate(lines):
        name_match = _NAME_RE.match(line)
        if name_match:
            current_name = name_match.group("name")
            continue

        slugs_match = _SLUGS_RE.match(line)
        if not slugs_match or current_name is None:
            continue

        current_slugs = _parse_items(slugs_match.group("items"))
        is_section_only = bool(current_slugs) and all(
            s.startswith("akinator-") for s in current_slugs
        )
        if not is_section_only:
            unchanged += 1
            continue

        new_slugs = match_specialties(current_name)
        if new_slugs == current_slugs:
            unchanged += 1
            continue

        indent = slugs_match.group("indent")
        new_line = f'{indent}"direction_slugs": {_render(new_slugs)},\n'
        if apply:
            lines[i] = new_line
        changed += 1
        print(f"  {current_name!r}: {current_slugs} -> {new_slugs}")

    if apply and changed:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    return changed, unchanged


def main(apply: bool) -> None:
    total_changed = 0
    total_unchanged = 0
    for rel_path in SEED_FILES:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel_path)
        if not os.path.exists(path):
            print(f"skip (not found): {rel_path}")
            continue
        print(f"\n=== {rel_path} ===")
        changed, unchanged = process_file(path, apply)
        total_changed += changed
        total_unchanged += unchanged

    print(f"\nTotal: {total_changed} rewritten, {total_unchanged} left as-is.")
    if not apply:
        print("Dry run only — re-run with --apply to write the files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes to the seed files")
    args = parser.parse_args()
    main(args.apply)
