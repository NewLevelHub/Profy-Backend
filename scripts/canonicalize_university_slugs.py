"""
SNAP-6 — one canonical `slug` for every university in the snapshot.

Curated rows historically used a now-removed transliteration
(`naczionalnyj`, `czk`, `-nyj`); jinaq rows and pass-2 keepers use the
current `scripts/seed_riasec_directions.slugify` (`natsionalnyy`, `ts`,
`-nyy`). Merged keepers also kept cluster-artifact slugs
(`griffith-university-aviation`). This rebuilds EVERY slug from the
university's name with the one canonical function, so slug is finally a
pure function of the data.

  slug = slugify(name)
  on collision: slug = f"{base}-{md5(stable-key)[:6]}"   (deterministic,
                not a positional "-2")

Two effects, both written by this script:
  * `--into <snapshot>`  — rewrites `slug` and `keys.slug` on every row.
  * `scripts/data/slug_rename_map.json`  — {old_slug: new_slug} for every
    row whose slug changed, consumed by scripts/rename_university_photos.py
    to move `<old>.webp` / `<old>.card.webp` in the media folder.

Run (plain python on the host), AFTER normalize + world-rank, BEFORE the
tag-map step:
  python scripts/canonicalize_university_slugs.py
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

# Kept byte-for-byte identical to scripts/seed_riasec_directions.slugify (the
# scheme jinaq's importer also uses). Inlined so this build-time tool stays
# pure-stdlib (no sqlalchemy import chain). If that function ever changes,
# change this too.
_CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(title: str) -> str:
    slug = (title or "").lower().replace("&", " and ")
    slug = "".join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_SNAPSHOT = os.path.join(_DIR, "university_snapshot.clean.json")
DEFAULT_RENAME_MAP = os.path.join(_DIR, "slug_rename_map.json")
DEFAULT_REPORT = os.path.join(_DIR, "slug_canonicalize_report.md")


def stable_key(u: dict) -> str:
    k = u.get("keys") or {}
    return (str(k.get("jinaq_id")) if k.get("jinaq_id")
            else k.get("ror_id") or u.get("slug")
            or f'{u.get("name","")}|{u.get("country","")}|{u.get("city","")}')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--into", default=DEFAULT_SNAPSHOT)
    ap.add_argument("--rename-map", default=DEFAULT_RENAME_MAP)
    ap.add_argument("--report", default=DEFAULT_REPORT)
    ap.add_argument("--indent", type=int, default=2)
    args = ap.parse_args()

    with open(args.into, encoding="utf-8") as f:
        data = json.load(f)
    unis = data["universities"]

    # base slug per row
    base = {}
    for u in unis:
        b = slugify(u.get("name") or "") or slugify(u.get("slug") or "") or "university"
        base[id(u)] = b

    # who collides on the same base
    by_base = defaultdict(list)
    for u in unis:
        by_base[base[id(u)]].append(u)

    new_slug: dict[int, str] = {}
    for b, group in by_base.items():
        if len(group) == 1:
            new_slug[id(group[0])] = b
            continue
        # deterministic: the row with the smallest stable_key keeps the bare
        # slug, the rest get a hash suffix.
        group_sorted = sorted(group, key=stable_key)
        new_slug[id(group_sorted[0])] = b
        for u in group_sorted[1:]:
            h = hashlib.md5(stable_key(u).encode("utf-8")).hexdigest()[:6]
            new_slug[id(u)] = f"{b}-{h}"

    rename_map: dict[str, str] = {}
    changed = 0
    for u in unis:
        old = u.get("slug")
        new = new_slug[id(u)]
        if old != new:
            changed += 1
            if old:
                rename_map[old] = new
        u["slug"] = new
        u.setdefault("keys", {})["slug"] = new

    data.setdefault("_meta", {})["slug_canonicalized"] = {
        "function": "scripts/seed_riasec_directions.slugify",
        "changed": changed,
        "collision_suffixes": sum(1 for v in new_slug.values() if v not in by_base),
    }

    with open(args.into, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=args.indent or None)
        f.write("\n")
    with open(args.rename_map, "w", encoding="utf-8") as f:
        json.dump(rename_map, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    coll = {b: [u["name"] for u in g] for b, g in by_base.items() if len(g) > 1}
    lines = [
        "# slug canonicalize report\n",
        f"universities: {len(unis)}",
        f"slugs changed: **{changed}**",
        f"rename-map entries (had an old slug): {len(rename_map)}",
        f"base-slug collisions resolved with a hash suffix: {len(coll)} groups\n",
    ]
    if coll:
        lines.append("## collision groups\n")
        for b, names in sorted(coll.items()):
            lines.append(f"- `{b}` — {', '.join(names)}")
    with open(args.report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(lines))
    print(f"\n[snapshot slugs rewritten in {args.into}]")
    print(f"[rename map -> {args.rename_map}]")
    print(f"[report -> {args.report}]")


if __name__ == "__main__":
    main()
