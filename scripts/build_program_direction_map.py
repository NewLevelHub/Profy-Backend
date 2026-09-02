"""
SNAP-4 (step 1) — seed scripts/data/program_direction_map.json, the single
canonical `program name -> [direction_slug]` dictionary that replaces
scripts/specialty_profession_map.py and
scripts/data/jinaq/specialty_direction_review.json.

Merges both existing hand-reviewed sources (union of slugs on a shared key),
keyed by a normalised program name. If program_direction_map.json already
exists, its `map` is merged on top (existing keys win, so HAND EDITS ARE
KEPT) unless --reseed. Then reports how far that gets us against
university_snapshot.clean.json: how many currently-untagged programs it would
tag, how many stay untagged, and the most frequent untagged names left for a
human to add to the map.

`category_fallback` (jinaq `source_category` -> [slug]) is left EMPTY — see
SNAP-4 step 3: whether a coarse-category fallback is acceptable is a
decision, not a default.

This does NOT touch the snapshot. Applying the map is
scripts/apply_program_direction_map.py.

Run (plain python on the host):
  python scripts/build_program_direction_map.py
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_OUT = os.path.join(_DIR, "program_direction_map.json")
DEFAULT_REPORT = os.path.join(_DIR, "program_direction_map_report.md")
SNAPSHOT = os.path.join(_DIR, "university_snapshot.clean.json")
REVIEW = os.path.join(_DIR, "jinaq", "specialty_direction_review.json")

_WS = re.compile(r"\s+")


def norm(s: str) -> str:
    return _WS.sub(" ", (s or "").strip().lower())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--report", default=DEFAULT_REPORT)
    ap.add_argument("--snapshot", default=SNAPSHOT)
    ap.add_argument("--top", type=int, default=120)
    ap.add_argument("--reseed", action="store_true",
                    help="rebuild from the two sources only, dropping any hand edits in the existing file")
    args = ap.parse_args()

    from scripts.specialty_profession_map import SPECIALTY_TO_PROFESSIONS, GARBAGE_SPECIALTIES

    merged: dict[str, set[str]] = {}
    garbage = {norm(g) for g in GARBAGE_SPECIALTIES}

    for name, slugs in SPECIALTY_TO_PROFESSIONS.items():
        k = norm(name)
        if k and k not in garbage:
            merged.setdefault(k, set()).update(slugs)

    with open(REVIEW, encoding="utf-8") as f:
        review = json.load(f)
    for s in review["specialties"]:
        if s.get("direction_slugs"):
            k = norm(s["name"])
            if k and k not in garbage:
                merged.setdefault(k, set()).update(s["direction_slugs"])

    kept_hand_keys = 0
    category_fallback = {}
    if not args.reseed and os.path.exists(args.out):
        prev_doc = json.load(open(args.out, encoding="utf-8"))
        for k, v in prev_doc.get("map", {}).items():
            if k not in merged:
                kept_hand_keys += 1
            merged.setdefault(k, set()).update(v)  # existing wins / adds
        category_fallback = prev_doc.get("category_fallback") or {}  # hand-maintained, kept as-is

    mapping = {k: sorted(v) for k, v in sorted(merged.items())}
    all_slugs = sorted({s for v in mapping.values() for s in v})

    payload = {
        "_meta": {
            "note": "program name (normalised) -> [direction_slug]. Merged from "
                    "specialty_profession_map.py + jinaq/specialty_direction_review.json, "
                    "plus hand-added keys. Applied by apply_program_direction_map.py --into <snapshot>.",
            "keys": len(mapping),
            "distinct_slugs": len(all_slugs),
        },
        "map": mapping,
        "category_fallback": category_fallback,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ---- coverage against the snapshot ------------------------------------------
    with open(args.snapshot, encoding="utf-8") as f:
        unis = json.load(f)["universities"]
    total = tagged_now = would_tag = still_untagged = 0
    untagged_names: Counter = Counter()
    untagged_by_cat: Counter = Counter()
    for u in unis:
        for p in u.get("programs") or []:
            total += 1
            if p.get("professions"):
                tagged_now += 1
                continue
            if norm(p["name"]) in mapping:
                would_tag += 1
            else:
                still_untagged += 1
                untagged_names[p["name"]] += 1
                untagged_by_cat[p.get("source_category") or "(none)"] += 1

    lines = [
        "# program_direction_map — build & coverage report\n",
        f"map keys: **{len(mapping)}**   distinct slugs: {len(all_slugs)}"
        + (f"   (kept {kept_hand_keys} hand-added keys)" if kept_hand_keys else "") + "\n",
        "## coverage against university_snapshot.clean.json\n",
        f"- total programs: {total}",
        f"- already tagged in snapshot: {tagged_now}",
        f"- **would be tagged by this map: {would_tag}**",
        f"- still untagged after the map: **{still_untagged}** "
        f"({still_untagged * 100 // total}%)\n",
        f"### top {args.top} untagged program names (add these to the map)\n",
    ]
    for name, n in untagged_names.most_common(args.top):
        lines.append(f"- {n:4}  {name}")
    lines.append("\n### untagged by source_category\n")
    for cat, n in untagged_by_cat.most_common():
        lines.append(f"- {cat}: {n}")
    with open(args.report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(lines[:9]))
    print(f"\n[map -> {args.out}]\n[report -> {args.report}]")


if __name__ == "__main__":
    main()
