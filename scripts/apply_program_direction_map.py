"""
SNAP-4 (step 2) — stamp profession tags onto programs in the snapshot from
scripts/data/program_direction_map.json.

First, PRUNE any profession slug on any program that is not a real
Direction (slugify of a title in riasec_professions.py) — keeps the snapshot
consistent with the catalogue after a profession is removed.

Then, for every program that STILL has NO `professions`:
  1. look up norm(program name) in `map`            -> use those slugs
  2. else look up `source_category` in `category_fallback` (if non-empty)
  3. else leave untagged (reported)

Only ever ADDS tags to empty programs — never overwrites a program that
already carries a valid hand-reviewed tag. Idempotent.

Writes back into `--into` (default university_snapshot.clean.json), the same
one-file model as build_world_rank_map.py --into.

Run AFTER build_program_direction_map.py, whenever the map has been extended:
  python scripts/apply_program_direction_map.py
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.canonicalize_university_slugs import slugify  # pure-stdlib
from scripts.riasec_professions import PROFESSIONS

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
VALID_SLUGS = {slugify(p["title"]) for p in PROFESSIONS}
DEFAULT_MAP = os.path.join(_DIR, "program_direction_map.json")
DEFAULT_SNAPSHOT = os.path.join(_DIR, "university_snapshot.clean.json")
DEFAULT_REPORT = os.path.join(_DIR, "program_direction_map_apply_report.md")

_WS = re.compile(r"\s+")


def norm(s: str) -> str:
    return _WS.sub(" ", (s or "").strip().lower())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default=DEFAULT_MAP)
    ap.add_argument("--into", default=DEFAULT_SNAPSHOT)
    ap.add_argument("--report", default=DEFAULT_REPORT)
    ap.add_argument("--indent", type=int, default=2)
    args = ap.parse_args()

    with open(args.map, encoding="utf-8") as f:
        md = json.load(f)
    name_map: dict[str, list[str]] = md["map"]
    cat_fallback: dict[str, list[str]] = md.get("category_fallback") or {}
    default_fallback: list[str] = md.get("default_fallback") or []

    with open(args.into, encoding="utf-8") as f:
        data = json.load(f)
    unis = data["universities"]

    by_name = by_cat = still = 0
    total = tagged_before = pruned = 0
    untagged_names: Counter = Counter()
    for u in unis:
        for p in u.get("programs") or []:
            total += 1
            if p.get("professions"):
                good = [s for s in p["professions"] if s in VALID_SLUGS]
                if len(good) != len(p["professions"]):
                    pruned += len(p["professions"]) - len(good)
                    p["professions"] = good
                if good:
                    tagged_before += 1
                    continue
            slugs = name_map.get(norm(p["name"]))
            if slugs:
                p["professions"] = sorted(set(slugs))
                by_name += 1
                continue
            slugs = cat_fallback.get(p.get("source_category") or "")
            if slugs:
                p["professions"] = sorted(set(slugs))
                by_cat += 1
                continue
            if default_fallback:
                p["professions"] = sorted(set(default_fallback))
                by_cat += 1
                continue
            still += 1
            untagged_names[p["name"]] += 1

    tagged_after = tagged_before + by_name + by_cat
    data.setdefault("_meta", {})["program_direction_map_applied"] = {
        "tagged_by_name": by_name, "tagged_by_category_fallback": by_cat,
        "still_untagged": still,
        "programs_with_tag": f"{tagged_after}/{total} ({tagged_after * 100 // total}%)",
    }
    with open(args.into, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=args.indent or None)
        f.write("\n")

    lines = [
        "# program_direction_map — apply report\n",
        f"- invalid profession tags pruned:    {pruned}",
        f"- newly tagged by name:              **{by_name}**",
        f"- newly tagged by category fallback: {by_cat}",
        f"- still untagged:                    **{still}** ({still * 100 // total}%)",
        f"- programs with >=1 tag now:         {tagged_after}/{total} ({tagged_after * 100 // total}%)\n",
        "## still-untagged names (frequency)\n",
    ]
    for name, n in untagged_names.most_common(200):
        lines.append(f"- {n:4}  {name}")
    with open(args.report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(lines[:6]))
    print(f"[snapshot updated in {args.into}]\n[report -> {args.report}]")


if __name__ == "__main__":
    main()
