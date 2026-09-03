"""
SNAP-7 (step 1) — list candidate "same university under an English name and
a Russian name" pairs still left after normalize pass 2, for a human to
confirm.

Pass 2 auto-merged only pairs with a hard identity signal (shared UNIRANKS
Global Rank or shared ror_id). The rest are found here by: same country,
same/near city, one name Latin-only + one with Cyrillic, AND a
transliterated stop-word-stripped name-core similarity above a threshold
(so "Stanford University" pairs with "Стэнфордский университет" but not with
every other university in the same city). Each Latin row keeps only its single
best Cyrillic match. Shared-ror_id pairs are always included regardless of
name. Everything is written UNCONFIRMED to
scripts/data/en_ru_university_merge.json — a reviewer sets `confirmed: true`
per pair (checking city / programs / ror_id like every other identity pass in
this repo), then normalize pass 3 applies them.

Rows whose name is a faculty / school / centre go to a separate `subunits`
list — those are a "merge into parent or keep separate" decision, not an
EN/RU rename.

Read-only. Run after normalize + world-rank + slug-canonicalize:
  python scripts/generate_en_ru_merge_review.py [--overwrite]
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SNAPSHOT = os.path.join(_DIR, "university_snapshot.clean.json")
OUT = os.path.join(_DIR, "en_ru_university_merge.json")

_WS = re.compile(r"\s+")
_CYR = re.compile(r"[а-яё]", re.I)
_LAT = re.compile(r"[a-z]", re.I)

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
# stop-words in either language that carry no identity
_STOP = {
    "university", "universities", "the", "of", "a", "college", "institute",
    "institution", "school", "national", "state", "academy", "faculty",
    "universitet", "universiteta", "universitete", "natsionalnyy", "gosudarstvennyy",
    "imeni", "im", "institut", "akademiya", "nauk", "nauchnyy", "issledovatelskiy",
    "and", "for", "in", "at",
}


def translit(s):
    s = (s or "").lower().replace("&", " and ")
    return "".join(_TRANSLIT.get(ch, ch) for ch in s)


def core_tokens(name, city=None):
    toks = re.findall(r"[a-z0-9]+", translit(name))
    drop = set(_STOP)
    if city:  # the city name is not identity — "Astana IT" vs "... Астана" must not match on it
        drop |= {t for t in re.findall(r"[a-z0-9]+", translit(city)) if len(t) >= 3}
    return {t for t in toks if t not in drop and len(t) >= 3}


def _fuzzy_jaccard(ca, cb):
    """|A∩B| / |A∪B| where two tokens count as shared if they are >=0.85
    similar (handles universitet/university, ё/е, im/imeni)."""
    if not ca or not cb:
        return 0.0
    shared = 0
    used = set()
    for x in ca:
        for y in cb:
            if y not in used and SequenceMatcher(None, x, y).ratio() >= 0.85:
                shared += 1
                used.add(y)
                break
    return shared / (len(ca) + len(cb) - shared)


def core_similarity(a_name, b_name, a_city=None, b_city=None):
    return _fuzzy_jaccard(core_tokens(a_name, a_city), core_tokens(b_name, b_city))
_SUBUNIT = re.compile(
    r"\b(Faculty|School of [A-ZА-Я]|College of|Graduate School|Business School|"
    r"Law School|Medical School|ILR School|Department|Centre for|Center for|"
    r"Scuola del|колледж|факультет)\b", re.I,
)


def norm(s):
    return _WS.sub(" ", (s or "").strip().lower())


def script(s):
    c, l = bool(_CYR.search(s or "")), bool(_LAT.search(s or ""))
    return "cyr" if c and not l else "lat" if l and not c else "mixed"


def loose_city(a, b):
    x, y = norm(a).split(",")[0].strip(), norm(b).split(",")[0].strip()
    return not x or not y or x == y or x in y or y in x


def side(u):
    return {
        "slug": u.get("slug"), "name": u["name"],
        "country": u.get("country"), "city": u.get("city"),
        "ror_id": u.get("ror_id"), "jinaq_id": (u.get("keys") or {}).get("jinaq_id"),
        "programs": len(u.get("programs") or []),
        "tagged_programs": sum(1 for p in u.get("programs") or [] if p.get("professions")),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", default=SNAPSHOT)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--overwrite", action="store_true",
                    help="replace an existing en_ru_university_merge.json (drops confirmations!)")
    ap.add_argument("--threshold", type=float, default=0.7,
                    help="min transliterated name-core fuzzy-Jaccard similarity (0..1)")
    args = ap.parse_args()

    if os.path.exists(args.out) and not args.overwrite:
        sys.exit(f"{args.out} exists — pass --overwrite to regenerate (loses `confirmed` flags)")

    with open(args.snapshot, encoding="utf-8") as f:
        unis = json.load(f)["universities"]

    by_country = defaultdict(list)
    for u in unis:
        by_country[norm(u.get("country"))].append(u)

    # Every university's single best same-city partner above threshold —
    # regardless of script. Catches Latin<->Cyrillic ("Stanford" / "Стэнфордский"),
    # "The X" / "X", and Russian<->Russian abbreviation/«им.» variants.
    pairs, subunits, seen = [], [], set()
    for rows in by_country.values():
        for i, u in enumerate(rows):
            best, best_score, best_ror = None, 0.0, False
            for j, v in enumerate(rows):
                if i == j or not loose_city(u.get("city"), v.get("city")):
                    continue
                ror = bool(u.get("ror_id")) and u.get("ror_id") == v.get("ror_id")
                score = core_similarity(u["name"], v["name"], u.get("city"), v.get("city"))
                if not (ror or score >= args.threshold):
                    continue
                if (ror and not best_ror) or (not best_ror and score > best_score):
                    best, best_score, best_ror = v, score, ror
            if best is None:
                continue
            key = frozenset((id(u), id(best)))
            if key in seen:
                continue
            seen.add(key)
            # order sides: Cyrillic name -> "ru", the other -> "en" (pass 3
            # keeps the Russian display name; for same-script pairs it keeps
            # the richer row's name).
            a, b = (u, best) if script(u["name"]) != "cyr" else (best, u)
            entry = {
                "confirmed": False,
                "hint": ("shared ror_id" if best_ror else f"name-core similarity {best_score:.2f}"),
                "en": side(a), "ru": side(b),
            }
            (subunits if _SUBUNIT.search(a["name"]) or _SUBUNIT.search(b["name"]) else pairs).append(entry)

    pairs.sort(key=lambda e: (0 if e["hint"] == "shared ror_id" else 1, e["en"]["name"]))
    payload = {
        "_meta": {
            "note": "SNAP-7. Set `confirmed: true` on a pair that is one institution; "
                    "normalize pass 3 keeps the Russian name, English -> aliases, keeper = "
                    "richer row. `subunits` need a separate merge-into-parent / keep decision.",
            "candidate_pairs": len(pairs), "candidate_subunits": len(subunits),
        },
        "pairs": pairs,
        "subunits": subunits,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"candidate EN/RU pairs: {len(pairs)}   candidate sub-units: {len(subunits)}")
    print(f"[-> {args.out}]  set `confirmed: true` per real pair, then run normalize")


if __name__ == "__main__":
    main()
