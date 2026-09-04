"""
Derive the CLEAN university snapshot from the raw one.

Input : scripts/data/university_snapshot.json          (raw export, untouched)
Output: scripts/data/university_snapshot.clean.json     (input for build_universities.py)
        scripts/data/university_snapshot_normalize_report.md

Does exactly three things, nothing else — no DB, no network:

  A. Strip rankings   — removes ranking / ranking_label / uniranks_kz_rank /
                        uniranks_world_rank / uniranks_note from every
                        university. Ranking is re-applied later by a separate
                        script, not carried in this snapshot.
  B. Strip cost       — removes cost_per_year / cost_label /
                        cost_per_year_min / cost_per_year_max /
                        cost_currency from every program (not shown to users).
  C.  Merge duplicates, pass 1 — a CURATED row and a JINAQ row for the same
      institution (Satbayev University / Satbayev University (Университет
      Сатпаева)). Rule (ALL): names match on norm(name) OR norm(name minus a
      trailing "(...)"); the group is exactly 2 rows; exactly one row has
      keys.jinaq_id; same country. Keeper = the curated row; it absorbs the
      other's programs / external_refs / jinaq_id / missing scalars.

  C2. Merge duplicates, pass 2 — the SAME institution under an English name
      AND a Russian name, BOTH from jinaq (Stanford University / Стэнфордский
      университет). Pass 1 can't see these: name strings differ, both carry a
      jinaq_id. Rule (ALL): same country; one name Latin-only, the other has
      Cyrillic; and a hard identity signal — shared ror_id, OR the exact same
      UNIRANKS Global Rank in the confirmed rows of
      uniranks_world_rank_review.json (a dense integer ranking does not tie
      two different same-country institutions and also hand them translated
      names). Keeper = the row with more data (ror_id > tagged programs >
      programs > lower jinaq_id); its display name is set to the RUSSIAN
      variant (the platform's audience reads Russian), the English name goes
      to `aliases`. A row that is a faculty/school (not the whole
      institution) is routed to manual review, never merged.

Anything not matching a rule is listed under "manual review" and left
untouched. Residual English/Russian pairs with no shared rank/ror_id are a
known remainder — see ticket SNAP-7.

Run (plain python on the host):
  python scripts/normalize_university_snapshot.py
      [--in scripts/data/university_snapshot.json]
      [--out scripts/data/university_snapshot.clean.json]
      [--report scripts/data/university_snapshot_normalize_report.md]
      [--indent 2]
"""
import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_IN = os.path.join(_DIR, "university_snapshot.json")
DEFAULT_OUT = os.path.join(_DIR, "university_snapshot.clean.json")
DEFAULT_REPORT = os.path.join(_DIR, "university_snapshot_normalize_report.md")
DEFAULT_RANK_REVIEW = os.path.join(_DIR, "uniranks_world_rank_review.json")

UNI_RANK_FIELDS = ("ranking", "ranking_label", "uniranks_kz_rank", "uniranks_world_rank", "uniranks_note")
PROG_COST_FIELDS = ("cost_per_year", "cost_label", "cost_per_year_min", "cost_per_year_max", "cost_currency")
UNI_FILL_SCALARS = ("website", "description", "short_name", "location", "source_url")
UNI_FILL_DICTS = ("contacts", "facilities", "fact_sources")

_WS = re.compile(r"\s+")
_PAREN_TAIL = re.compile(r"\s*\([^()]*\)\s*$")
_DEGREE_SUFFIX = re.compile(
    r"\s*\((?:бакалавр(?:,\s*[^)]*)?|магистратура|практический психолог)\)\s*", re.IGNORECASE
)


def norm(s):
    return _WS.sub(" ", (s or "").strip().lower())


def strip_paren(s):
    prev = norm(s)
    while True:
        cur = _PAREN_TAIL.sub("", prev).strip()
        if cur == prev:
            return cur
        prev = cur


def norm_program(s):
    return _WS.sub(" ", _DEGREE_SUFFIX.sub(" ", (s or "")).strip().lower())


def has_jinaq(u):
    return bool(u.get("keys", {}).get("jinaq_id"))


def label(u):
    return f'{u["name"]} [{u.get("city") or "?"}, {u.get("country") or "?"}]' \
           f'{" slug=" + u["slug"] if u.get("slug") else ""}'


class Report:
    def __init__(self):
        self.b = io.StringIO()

    def w(self, s=""):
        self.b.write(s + "\n")

    def __str__(self):
        return self.b.getvalue()


def merge_into(keeper, absorbed):
    """Fold `absorbed` into `keeper` in place. Returns (added, collisions, filled_fields)."""
    keeper.setdefault("keys", {})
    if absorbed.get("keys", {}).get("jinaq_id"):
        keeper["keys"]["jinaq_id"] = absorbed["keys"]["jinaq_id"]

    keeper.setdefault("external_refs", [])
    seen = {(r["source"], r["external_id"]) for r in keeper["external_refs"]}
    for r in absorbed.get("external_refs", []):
        if (r["source"], r["external_id"]) not in seen:
            keeper["external_refs"].append(r)
            seen.add((r["source"], r["external_id"]))

    filled = []
    for f in UNI_FILL_SCALARS:
        if not keeper.get(f) and absorbed.get(f):
            keeper[f] = absorbed[f]
            filled.append(f)
    if not keeper.get("aliases") and absorbed.get("aliases"):
        keeper["aliases"] = absorbed["aliases"]
        filled.append("aliases")
    for f in UNI_FILL_DICTS:
        base = dict(keeper.get(f) or {})
        for k, v in (absorbed.get(f) or {}).items():
            if k not in base:
                base[k] = v
        if base != (keeper.get(f) or {}):
            keeper[f] = base
            filled.append(f)

    have = {norm_program(p["name"]) for p in keeper.get("programs", [])}
    added = collisions = 0
    for p in absorbed.get("programs", []):
        key = norm_program(p["name"])
        if key in have:
            collisions += 1
        else:
            keeper.setdefault("programs", []).append(p)
            have.add(key)
            added += 1
    keeper["programs"].sort(key=lambda p: p.get("name") or "")
    return added, collisions, filled


# ---------------------------------------------------------------------------
# Pass 2 — same institution under an English name AND a Russian name, both
# imported from jinaq (Stanford University / Стэнфордский университет). Pass 1
# can't see these: the name strings differ and both rows carry a jinaq_id.
# ---------------------------------------------------------------------------
_CYR = re.compile(r"[а-яё]", re.I)
_LAT = re.compile(r"[a-z]", re.I)
# A row whose name is a specific faculty / school / college / research centre,
# not the whole institution — routed to manual review, never auto-merged.
# Deliberately does NOT trip on a bare comma or lone dash: real institution
# names carry them ("University of California, Berkeley", "Карнеги — Меллон").
_SUBUNIT = re.compile(
    r"\b(Faculty|School of [A-ZА-Я]|College of|Graduate School|Business School|"
    r"Law School|Medical School|ILR School|Department|Centre for|Center for|"
    r"Scuola del|колледж|факультет|Yong Loo)\b",
    re.I,
)


def _script(s):
    s = s or ""
    c, l = bool(_CYR.search(s)), bool(_LAT.search(s))
    return "cyr" if c and not l else "lat" if l and not c else "mixed"


def _rank_name(s):
    """Name key for the rank lookup — drops a leading article so
    'The University of Manchester' and 'University of Manchester' agree.
    Never merges distinct institutions (an article is not identity)."""
    return re.sub(r"^(the|der|die|das|la|le|les|el)\s+", "", norm(s))


def _load_rank_lookup(path):
    """{(norm name, norm country): UNIRANKS world_rank} from the CONFIRMED
    entries of uniranks_world_rank_review.json. Read straight from the review
    file (not world_rank.json) so this signal is stable regardless of how far
    the dedup has progressed — the review file has a separate entry for the
    English name and the Russian name of the same institution, each carrying
    the same rank, which is exactly what pass 2 needs to pair them."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return out
    for e in data:
        if e.get("confirmed") is not True or e.get("world_rank") is None:
            continue
        out[(_rank_name(e.get("our_name")), norm(e.get("country")))] = int(e["world_rank"])
    return out


def _richness(u):
    tagged = sum(1 for p in u["programs"] if p.get("professions"))
    return (bool(u.get("ror_id")), tagged, len(u["programs"]),
            -int((u.get("keys") or {}).get("jinaq_id") or 10 ** 9))


def _do_en_ru_merge(a, b):
    """Fold the duplicate pair (a, b) into one row: keeper = the richer row.
    Display name: the Cyrillic one if exactly one side is Cyrillic (the
    platform's audience reads Russian), otherwise the keeper's own name. The
    other name + the absorbed slug go to `aliases`; the keeper's own jinaq_id
    is preserved for the deterministic PK. Returns (keeper, absorbed_id,
    kept_name, dropped_name, programs_added, programs_collided)."""
    keeper, absorbed = sorted([a, b], key=_richness, reverse=True)
    scripts = {_script(a["name"]), _script(b["name"])}
    if scripts == {"lat", "cyr"}:
        kept_name = a["name"] if _script(a["name"]) == "cyr" else b["name"]
        dropped_name = a["name"] if _script(a["name"]) == "lat" else b["name"]
    else:
        kept_name, dropped_name = keeper["name"], absorbed["name"]
    kept_jinaq = (keeper.get("keys") or {}).get("jinaq_id")
    added, coll, _ = merge_into(keeper, absorbed)
    if kept_jinaq:
        keeper["keys"]["jinaq_id"] = kept_jinaq
    keeper.setdefault("aliases", [])
    for extra in (dropped_name, absorbed.get("slug")):
        if extra and extra not in keeper["aliases"]:
            keeper["aliases"].append(extra)
    keeper["name"] = kept_name
    return keeper, id(absorbed), kept_name, dropped_name, added, coll


def merge_confirmed_en_ru(unis, review_path):
    """PASS 3 — apply the human-confirmed pairs from
    en_ru_university_merge.json (SNAP-7). Resolves each side by `slug` in the
    current `unis` list; skips a pair whose either side is already gone
    (merged by an earlier pass / a prior confirmation)."""
    try:
        with open(review_path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return unis, [], 0
    by_jinaq = {(u.get("keys") or {}).get("jinaq_id"): u for u in unis if (u.get("keys") or {}).get("jinaq_id")}
    by_name = {}
    for u in unis:
        by_name.setdefault((norm(u["name"]), norm(u.get("country"))), u)
        by_name.setdefault((norm(u["name"]), None), u)

    def resolve(sd):
        """Resolve a review side dict to a current uni — jinaq_id first (stable
        across slug canonicalization), then exact name (+country)."""
        if sd.get("jinaq_id") and sd["jinaq_id"] in by_jinaq:
            return by_jinaq[sd["jinaq_id"]]
        return (by_name.get((norm(sd.get("name")), norm(sd.get("country"))))
                or by_name.get((norm(sd.get("name")), None)))

    removed, rows = set(), []
    confirmed = [p for p in (data.get("pairs", []) + data.get("subunits", []))
                 if p.get("confirmed") is True]
    for p in confirmed:
        a = resolve(p.get("en") or p.get("a") or {})
        b = resolve(p.get("ru") or p.get("b") or {})
        if a is None or b is None or a is b or id(a) in removed or id(b) in removed:
            continue
        _, absorbed_id, kept_name, dropped_name, added, coll = _do_en_ru_merge(a, b)
        removed.add(absorbed_id)
        rows.append({"kept": kept_name, "dropped_en": dropped_name,
                     "programs_added": added, "programs_collided": coll})
    return [u for u in unis if id(u) not in removed], rows, len(confirmed)


def merge_en_ru_pairs(unis, rank_lookup):
    """Returns (new_unis, merge_rows, review_rows)."""
    def rank_of(u):
        for nm in (u.get("name"), *(u.get("aliases") or [])):
            rk = rank_lookup.get((_rank_name(nm), norm(u.get("country"))))
            if rk is not None:
                return rk
        return None

    by_country = defaultdict(list)
    for u in unis:
        by_country[norm(u.get("country"))].append(u)

    removed = set()
    merges, review = [], []
    for rows in by_country.values():
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if id(a) in removed or id(b) in removed:
                    continue
                if {_script(a["name"]), _script(b["name"])} != {"lat", "cyr"}:
                    continue
                ror_match = bool(a.get("ror_id")) and a.get("ror_id") == b.get("ror_id")
                ra, rb = rank_of(a), rank_of(b)
                rank_match = ra is not None and ra == rb
                if not (ror_match or rank_match):
                    continue
                pair = [label(a), label(b)]
                if _SUBUNIT.search(a["name"]) or _SUBUNIT.search(b["name"]):
                    review.append((f"en/ru, one side is a faculty/school ({'ror_id' if ror_match else 'rank ' + str(ra)})", pair))
                    continue
                # Same country + EN/RU name split + an EXACT shared UNIRANKS
                # Global Rank is definitional identity — a dense integer
                # ranking does not tie two different same-country universities
                # and also hand them translated names. City-string mismatches
                # here ("Бостон" vs "Кембридж" for MIT) are jinaq data errors,
                # not evidence of two institutions. Cross-country coincidences
                # are already excluded by the per-country grouping above.
                keeper, absorbed_id, cyr_name, lat_name, added, coll = _do_en_ru_merge(a, b)
                removed.add(absorbed_id)
                merges.append({
                    "kept": f'{cyr_name} [{keeper.get("city")}, {keeper.get("country")}] slug={keeper.get("slug")}',
                    "dropped_en": lat_name,
                    "signal": "ror_id" if ror_match else f"world_rank={ra}",
                    "programs_added": added, "programs_collided": coll,
                })
    return [u for u in unis if id(u) not in removed], merges, review


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--report", default=DEFAULT_REPORT)
    ap.add_argument("--rank-review", default=DEFAULT_RANK_REVIEW,
                    help="uniranks_world_rank_review.json — confirmation signal for pass 2")
    ap.add_argument("--en-ru-merge", default=os.path.join(_DIR, "en_ru_university_merge.json"),
                    help="human-confirmed EN/RU pairs for pass 3 (SNAP-7)")
    ap.add_argument("--indent", type=int, default=2)
    args = ap.parse_args()

    with open(args.inp, encoding="utf-8") as f:
        data = json.load(f)
    unis = data["universities"]

    before_u = len(unis)
    before_p = sum(len(u["programs"]) for u in unis)

    # ---- A + B: strip fields --------------------------------------------------
    stripped_rank = stripped_cost = 0
    for u in unis:
        for fld in UNI_RANK_FIELDS:
            if fld in u:
                del u[fld]
                stripped_rank += 1
        for p in u["programs"]:
            for fld in PROG_COST_FIELDS:
                if fld in p:
                    del p[fld]
                    stripped_cost += 1

    # ---- C: find merge candidates ------------------------------------------------
    auto_pairs = []           # (keeper_idx, absorbed_idx)
    manual = []               # (reason, [labels])
    seen_pair = set()
    seen_group = set()

    for keyfn, gl in ((lambda u: norm(u["name"]), "name"),
                      (lambda u: strip_paren(u["name"]), "name-no-paren")):
        groups = defaultdict(list)
        for i, u in enumerate(unis):
            groups[keyfn(u)].append(i)
        for gkey, idxs in groups.items():
            if len(idxs) < 2 or (gl, gkey) in seen_group:
                continue
            seen_group.add((gl, gkey))
            if len(idxs) != 2:
                manual.append((f"group of {len(idxs)} ({gl})", [label(unis[i]) for i in idxs]))
                continue
            a, b = idxs
            ua, ub = unis[a], unis[b]
            ja, jb = has_jinaq(ua), has_jinaq(ub)
            if ja == jb:
                manual.append((f"both {'have' if ja else 'lack'} jinaq_id ({gl})",
                               [label(ua), label(ub)]))
                continue
            if norm(ua.get("country")) != norm(ub.get("country")):
                manual.append((f"different country ({gl})", [label(ua), label(ub)]))
                continue
            keeper, absorbed = (a, b) if not ja else (b, a)
            pair_id = frozenset((keeper, absorbed))
            if pair_id in seen_pair:
                continue
            seen_pair.add(pair_id)
            auto_pairs.append((keeper, absorbed))

    # ---- C: apply merges -------------------------------------------------------
    removed = set()
    merge_rows = []
    for keeper, absorbed in auto_pairs:
        if keeper in removed or absorbed in removed:
            manual.append(("skipped — row already merged in another pair",
                           [label(unis[keeper]), label(unis[absorbed])]))
            continue
        k, a = unis[keeper], unis[absorbed]
        added, collisions, filled = merge_into(k, a)
        removed.add(absorbed)
        merge_rows.append({
            "keeper": label(k), "keeper_slug": k.get("slug"),
            "absorbed": label(a), "absorbed_jinaq_id": a.get("keys", {}).get("jinaq_id"),
            "programs_added": added, "programs_collided": collisions, "filled": filled,
        })

    unis = [u for i, u in enumerate(unis) if i not in removed]
    after_pass1 = len(unis)

    # ---- C2: English/Russian jinaq duplicates, hard signal (rank / ror_id) ---
    rank_lookup = _load_rank_lookup(args.rank_review)
    unis, enru_merges, enru_review = merge_en_ru_pairs(unis, rank_lookup)

    # ---- C3: English/Russian pairs a human confirmed (SNAP-7) ----------------
    unis, enru3_merges, enru3_confirmed = merge_confirmed_en_ru(unis, args.en_ru_merge)

    unis.sort(key=lambda r: (r.get("country") or "", r.get("name") or "", r.get("slug") or ""))

    after_p = sum(len(u["programs"]) for u in unis)
    tagged_p = sum(1 for u in unis for p in u["programs"] if p.get("professions"))

    data["universities"] = unis
    data.setdefault("_meta", {})["normalized"] = {
        "rankings_stripped": True,
        "cost_stripped": True,
        "universities_merged_pass1": len(merge_rows),
        "universities_merged_pass2_en_ru": len(enru_merges),
        "universities_merged_pass3_confirmed": len(enru3_merges),
        "counts": {"universities": len(unis), "programs": after_p,
                   "programs_with_profession_tag": tagged_p},
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=args.indent or None,
                  separators=None if args.indent else (",", ":"))
        f.write("\n")

    # ---- report -------------------------------------------------------------------
    r = Report()
    r.w("# University snapshot — normalize report\n")
    r.w(f"Input : `{args.inp}`")
    r.w(f"Output: `{args.out}`\n")
    r.w("## A/B — stripped fields\n")
    r.w(f"- ranking fields removed: {stripped_rank} (from universities)")
    r.w(f"- cost fields removed: {stripped_cost} (from programs)\n")
    r.w("## C — duplicate universities merged\n")
    r.w(f"**{len(merge_rows)} auto-merges.**\n")
    for m in merge_rows:
        r.w(f"- **keep** {m['keeper']}")
        r.w(f"  **absorb** {m['absorbed']}  (jinaq_id={m['absorbed_jinaq_id']})")
        r.w(f"  → +{m['programs_added']} programs, {m['programs_collided']} name-collisions skipped"
            + (f", filled: {', '.join(m['filled'])}" if m["filled"] else ""))
    r.w()
    r.w(f"## C — same-name groups NOT merged (manual review): {len(manual)}\n")
    for reason, labels in manual:
        r.w(f"- _{reason}_")
        for l in labels:
            r.w(f"  - {l}")
    r.w()
    r.w("## C2 — English-name / Russian-name jinaq duplicates\n")
    r.w(f"rank signal (confirmed uniranks_world_rank_review entries): {len(rank_lookup)}\n")
    r.w(f"**{len(enru_merges)} auto-merges** "
        f"(kept the Russian name, English name → `aliases`):\n")
    for m in enru_merges:
        r.w(f"- **keep** {m['kept']}")
        r.w(f"  drop EN name → alias: _{m['dropped_en']}_  · signal: {m['signal']}"
            f"  · +{m['programs_added']} programs, {m['programs_collided']} collisions")
    r.w()
    r.w(f"### C2 — need manual review: {len(enru_review)}\n")
    for reason, labels in enru_review:
        r.w(f"- _{reason}_")
        for l in labels:
            r.w(f"  - {l}")
    r.w()
    r.w("## C3 — human-confirmed EN/RU pairs (SNAP-7)\n")
    r.w(f"confirmed in en_ru_university_merge.json: {enru3_confirmed}   applied: **{len(enru3_merges)}**\n")
    for m in enru3_merges:
        r.w(f"- keep _{m['kept']}_  ← drop _{m['dropped_en']}_  "
            f"(+{m['programs_added']} programs, {m['programs_collided']} collisions)")
    r.w()
    r.w("## Totals\n")
    r.w(f"| | before | after pass 1 | after pass 3 |")
    r.w(f"|---|---|---|---|")
    r.w(f"| universities | {before_u} | {after_pass1} | {len(unis)} |")
    r.w(f"| programs | {before_p} | — | {after_p} |")
    r.w(f"| programs with profession tag | — | — | {tagged_p} ({tagged_p * 100 // after_p if after_p else 0}%) |")

    with open(args.report, "w", encoding="utf-8") as f:
        f.write(str(r))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(str(r))
    print(f"[clean snapshot -> {args.out}]")
    print(f"[report -> {args.report}]")


if __name__ == "__main__":
    main()
