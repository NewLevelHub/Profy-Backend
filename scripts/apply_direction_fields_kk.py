#!/usr/bin/env python
"""
KZ-504: Apply Kazakh translations for the direction list fields
`skills_needed` / `first_steps` into `direction_content_review_kk.json`.

Reads batch files `scripts/data/kk_done_dir/{skills,first_steps}_*.json`, each a
list of `{"slug", "field", "_index", "kk"}` records, and writes them
positionally into the matching direction entry. The list is padded to length
against the RU source first, so a partially-translated field keeps its RU tail
(documented interim, same as `_bootstrap_kk_from_ru`).

Idempotent. Run from repo root (no DB needed):
    python scripts/apply_direction_fields_kk.py
    python scripts/apply_direction_fields_kk.py --glob 'skills_*.json'
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).parent
RU_FILE = HERE / "direction_content_review.json"
KK_FILE = HERE / "direction_content_review_kk.json"
BATCH_DIR = HERE / "data" / "kk_done_dir"

KK_CHARS = set("әғқңөұүһі")
FIELDS = ("skills_needed", "first_steps", "subjects_to_develop")


def is_kazakh(text: str) -> bool:
    if not text or len(text) < 4:
        return True
    non_latin = 0
    kk = 0
    for w in text.split():
        if all(c.isalpha() and c.isascii() for c in w):
            continue
        non_latin += 1
        if any(c in KK_CHARS for c in w):
            kk += 1
    return non_latin == 0 or kk / non_latin >= 0.25


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="skills_*.json,first_steps_*.json")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    ru_by = {d["slug"]: d for d in json.loads(RU_FILE.read_text(encoding="utf-8"))}
    kk = json.loads(KK_FILE.read_text(encoding="utf-8"))
    kk_by = {d["slug"]: d for d in kk}

    patterns = [p.strip() for p in args.glob.split(",") if p.strip()]
    files: list[Path] = []
    for pat in patterns:
        files.extend(sorted(BATCH_DIR.glob(pat)))

    applied = 0
    invalid: list[dict] = []
    for bf in files:
        for rec in json.loads(bf.read_text(encoding="utf-8")):
            slug, field, idx, val = (
                rec["slug"], rec["field"], rec["_index"], rec["kk"],
            )
            if field not in FIELDS:
                continue
            if not is_kazakh(val):
                rec["_file"] = bf.name
                invalid.append(rec)
                continue
            src = ru_by.get(slug, {})
            dst = kk_by.get(slug)
            if dst is None:
                continue
            lst = dst.get(field) or []
            target_len = max(len(src.get(field, [])), idx + 1)
            while len(lst) < target_len:
                lst.append(src.get(field, [""] * target_len)[len(lst)]
                           if len(lst) < len(src.get(field, [])) else "")
            if lst[idx] != val:
                lst[idx] = val
                applied += 1
            dst[field] = lst

    KK_FILE.write_text(
        json.dumps(kk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Applied {applied} list-item translations from {len(files)} file(s).")
    if invalid:
        print(f"  {len(invalid)} rejected (failed kk check):")
        for r in invalid[:20]:
            print(f"    {r['_file']} {r['slug']}#{r['field']}#{r['_index']}: {r['kk'][:60]}")
        if args.report:
            Path(args.report).write_text(
                json.dumps(invalid, ensure_ascii=False, indent=2), encoding="utf-8"
            )


if __name__ == "__main__":
    main()
