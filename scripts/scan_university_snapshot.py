"""
Read-only quality scan of scripts/data/university_snapshot.json.

Reports only — writes no DB, changes no data, fixes nothing. Produces a
markdown report of what is wrong / thin / duplicated in the current
university + program catalogue, so we know what to clean before the snapshot
becomes the single source of truth.

Checks:
  1. Duplicate universities   — exact name, name+city, shared ror_id,
                                shared jinaq_id, name-without-parenthetical,
                                slug base (the "griffith-university-aviation"
                                pattern)
  2. University ranking gaps  — no ranking at all, ranking_label set but
                                ranking NULL, uniranks coverage
  3. University data gaps     — missing website / city / country /
                                description, zero programs
  4. Duplicate programs       — within one university, by exact name and by
                                degree-suffix-normalised name
  5. Untagged programs        — no `professions`; broken down by country,
                                source_category, and worst universities
  6. Invalid profession slugs — a program tag that is not one of the 145
                                Direction slugs
  7. Profession coverage      — professions with 0 / <3 tagged programs, and
                                professions whose tagged universities are all
                                unranked
  8. Program cost gaps        — no cost_per_year / cost_label / cost range

Run (plain python on the host — needs only the JSON file and, for check 6,
the list of Direction slugs):
  python scripts/scan_university_snapshot.py \
      [--snapshot scripts/data/university_snapshot.json] \
      [--slugs /tmp/direction_slugs.txt] \
      [--out scripts/data/university_snapshot_scan.md] [--top N]
"""
import argparse
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

DEFAULT_SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "university_snapshot.json")
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "university_snapshot_scan.md")

_WS = re.compile(r"\s+")
_PAREN_TAIL = re.compile(r"\s*\([^()]*\)\s*$")
# Same degree-level suffixes app/models/program.py's name_normalized strips.
_DEGREE_SUFFIX = re.compile(
    r"\s*\((?:бакалавр(?:,\s*[^)]*)?|магистратура|практический психолог)\)\s*",
    re.IGNORECASE,
)
_SLUG_TAIL = re.compile(r"-(?:aviation|finance|design|law|it|business|campus|branch|\d+)$")


def norm(s: str | None) -> str:
    return _WS.sub(" ", (s or "").strip().lower())


def strip_paren(s: str | None) -> str:
    prev = norm(s)
    while True:
        cur = _PAREN_TAIL.sub("", prev).strip()
        if cur == prev:
            return cur
        prev = cur


def norm_program(s: str | None) -> str:
    return _WS.sub(" ", _DEGREE_SUFFIX.sub(" ", (s or "")).strip().lower())


class Report:
    def __init__(self) -> None:
        self.buf = io.StringIO()

    def h(self, text: str) -> None:
        self.buf.write(f"\n## {text}\n\n")

    def p(self, text: str = "") -> None:
        self.buf.write(text + "\n")

    def bullet(self, text: str) -> None:
        self.buf.write(f"- {text}\n")

    def __str__(self) -> str:
        return self.buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", default=DEFAULT_SNAPSHOT)
    ap.add_argument("--slugs", default="/tmp/direction_slugs.txt",
                    help="newline-separated list of valid Direction slugs (for check 6)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--top", type=int, default=25, help="how many rows to list per section")
    args = ap.parse_args()

    with open(args.snapshot, encoding="utf-8") as f:
        data = json.load(f)
    unis: list[dict] = data["universities"]
    top = args.top

    valid_slugs: set[str] = set()
    if os.path.exists(args.slugs):
        with open(args.slugs, encoding="utf-8") as f:
            valid_slugs = {ln.strip() for ln in f if ln.strip()}

    r = Report()
    r.p(f"# University snapshot quality scan\n")
    r.p(f"Source: `{args.snapshot}`  ")
    r.p(f"Exported: {data.get('_meta', {}).get('exported_at', '?')}\n")

    total_progs = sum(len(u["programs"]) for u in unis)
    r.p(f"**{len(unis)} universities, {total_progs} programs.**")

    # ---------------------------------------------------------------- 1. dup unis
    r.h("1. Duplicate universities (candidate groups)")

    def group_by(keyfn, label):
        groups = defaultdict(list)
        for u in unis:
            k = keyfn(u)
            if k:
                groups[k].append(u)
        dups = {k: v for k, v in groups.items() if len(v) > 1}
        n_rows = sum(len(v) for v in dups.values())
        r.p(f"### by {label}: {len(dups)} groups, {n_rows} rows\n")
        for k, v in sorted(dups.items(), key=lambda kv: -len(kv[1]))[:top]:
            names = " | ".join(
                f'{x["name"]} [{x.get("city") or "?"}, {x.get("country") or "?"}]'
                f'{" slug=" + x["slug"] if x.get("slug") else ""}'
                for x in v
            )
            r.bullet(f"`{k}` ×{len(v)} — {names}")
        r.p()
        return dups

    group_by(lambda u: norm(u.get("name")), "exact normalised name")
    group_by(lambda u: (norm(u.get("name")), norm(u.get("city"))), "name + city")
    group_by(lambda u: u.get("ror_id"), "shared ror_id")
    group_by(lambda u: u["keys"].get("jinaq_id"), "shared jinaq_id (should be 0)")
    group_by(lambda u: strip_paren(u.get("name")) if _PAREN_TAIL.search(norm(u.get("name")) or "") or True else None,
             "name without trailing (...)")
    group_by(lambda u: _SLUG_TAIL.sub("", u["slug"]) if u.get("slug") and _SLUG_TAIL.search(u["slug"]) else None,
             "slug base (…-aviation / …-finance / …-2)")

    # ---------------------------------------------------------------- 2. rankings
    r.h("2. University ranking gaps")
    has_ranking = [u for u in unis if u.get("ranking") is not None]
    has_label = [u for u in unis if u.get("ranking_label")]
    label_no_num = [u for u in unis if u.get("ranking_label") and u.get("ranking") is None]
    has_uw = [u for u in unis if u.get("uniranks_world_rank") is not None]
    has_ukz = [u for u in unis if u.get("uniranks_kz_rank") is not None]
    any_rank = [u for u in unis if u.get("ranking") is not None or u.get("uniranks_world_rank") is not None]
    prog_no_rank = [u for u in unis if u["programs"] and u.get("ranking") is None and u.get("uniranks_world_rank") is None]
    r.bullet(f"`ranking` set: **{len(has_ranking)}** / {len(unis)}")
    r.bullet(f"`ranking_label` set: {len(has_label)}  (of those, **{len(label_no_num)}** have a label but NULL `ranking` — parse gaps)")
    r.bullet(f"`uniranks_world_rank` set: {len(has_uw)}   `uniranks_kz_rank` set: {len(has_ukz)}")
    r.bullet(f"**any** rank signal (ranking OR uniranks_world_rank): {len(any_rank)}")
    r.bullet(f"universities that HAVE programs but NO rank at all (sort last on every profession page): **{len(prog_no_rank)}**")
    if label_no_num:
        r.p("\nSample `ranking_label` present but `ranking` NULL:")
        for u in label_no_num[:top]:
            r.bullet(f'{u["name"]} — "{u["ranking_label"]}"')

    # ---------------------------------------------------------------- 3. data gaps
    r.h("3. University data gaps")
    for field in ("website", "city", "country", "description"):
        missing = [u for u in unis if not u.get(field)]
        r.bullet(f"no `{field}`: **{len(missing)}**"
                 + (f"  e.g. {', '.join(x['name'] for x in missing[:5])}" if missing else ""))
    zero_prog = [u for u in unis if not u["programs"]]
    r.bullet(f"zero programs: **{len(zero_prog)}**"
             + (f"  e.g. {', '.join(x['name'] for x in zero_prog[:8])}" if zero_prog else ""))
    weird_country = Counter(u.get("country") for u in unis)
    rare = [(c, n) for c, n in weird_country.items() if n <= 2]
    if rare:
        r.p(f"\nCountries with ≤2 universities ({len(rare)} distinct — possible typos/variants):")
        r.p(", ".join(f'"{c}"×{n}' for c, n in sorted(rare)))

    # ---------------------------------------------------------------- 4. dup programs
    r.h("4. Duplicate programs within one university")
    exact_dup_groups = 0
    exact_dup_rows = 0
    norm_dup_groups = 0
    norm_dup_rows = 0
    examples: list[str] = []
    for u in unis:
        by_exact = defaultdict(list)
        by_norm = defaultdict(list)
        for p in u["programs"]:
            by_exact[norm(p["name"])].append(p["name"])
            by_norm[norm_program(p["name"])].append(p["name"])
        for k, v in by_exact.items():
            if len(v) > 1:
                exact_dup_groups += 1
                exact_dup_rows += len(v)
        for k, v in by_norm.items():
            if len(v) > 1 and len(set(v)) > 1:  # different literal names, same normalised
                norm_dup_groups += 1
                norm_dup_rows += len(v)
                if len(examples) < top:
                    examples.append(f'{u["name"]}: {" / ".join(sorted(set(v)))}')
    r.bullet(f"exact same program name twice in one university: **{exact_dup_groups}** groups ({exact_dup_rows} rows)")
    r.bullet(f"same degree-suffix-normalised name, different literal text: **{norm_dup_groups}** groups ({norm_dup_rows} rows)")
    if examples:
        r.p("\nSample normalised-collision pairs:")
        for e in examples:
            r.bullet(e)

    # ---------------------------------------------------------------- 5. untagged
    r.h("5. Untagged programs (no profession → invisible to profession search)")
    untagged = [(u, p) for u in unis for p in u["programs"] if not p.get("professions")]
    r.bullet(f"untagged programs: **{len(untagged)}** / {total_progs} ({len(untagged)*100//total_progs}%)")
    by_country = Counter(u.get("country") for u, _ in untagged)
    r.p("\nBy country (top):")
    for c, n in by_country.most_common(15):
        r.bullet(f"{c or '?'}: {n}")
    by_cat = Counter(p.get("source_category") for _, p in untagged)
    r.p("\nBy source_category:")
    for c, n in by_cat.most_common(20):
        r.bullet(f"{c or '(none)'}: {n}")
    by_uni = Counter(u["name"] for u, _ in untagged)
    r.p("\nWorst universities (most untagged programs):")
    for name, n in by_uni.most_common(top):
        r.bullet(f"{name}: {n}")

    # ---------------------------------------------------------------- 6. bad slugs
    r.h("6. Profession tags pointing at unknown slugs")
    if not valid_slugs:
        r.p(f"_skipped — no slug list at `{args.slugs}`._")
    else:
        used = Counter(s for u in unis for p in u["programs"] for s in p.get("professions", []))
        unknown = {s: n for s, n in used.items() if s not in valid_slugs}
        r.bullet(f"distinct slugs used: {len(used)}  |  valid Direction slugs: {len(valid_slugs)}")
        r.bullet(f"**unknown slugs referenced: {len(unknown)}** ({sum(unknown.values())} tag rows)")
        for s, n in sorted(unknown.items(), key=lambda kv: -kv[1]):
            r.bullet(f"`{s}` ×{n}")

    # ---------------------------------------------------------------- 7. coverage
    r.h("7. Profession coverage")
    prog_per_slug = Counter()
    uni_per_slug = defaultdict(set)
    ranked_uni_per_slug = defaultdict(set)
    for u in unis:
        ranked = u.get("ranking") is not None or u.get("uniranks_world_rank") is not None
        for p in u["programs"]:
            for s in p.get("professions", []):
                prog_per_slug[s] += 1
                uni_per_slug[s].add(u["name"])
                if ranked:
                    ranked_uni_per_slug[s].add(u["name"])
    check_slugs = valid_slugs or set(prog_per_slug)
    zero = sorted(s for s in check_slugs if prog_per_slug[s] == 0)
    thin = sorted((prog_per_slug[s], s) for s in check_slugs if 0 < prog_per_slug[s] < 3)
    no_ranked = sorted(s for s in check_slugs if prog_per_slug[s] > 0 and not ranked_uni_per_slug[s])
    r.bullet(f"professions with **0** tagged programs (student picks it → empty page): **{len(zero)}**")
    if zero:
        r.p("  " + ", ".join(zero))
    r.bullet(f"professions with 1–2 tagged programs: **{len(thin)}**")
    for n, s in thin:
        r.bullet(f"  {s}: {n}")
    r.bullet(f"professions whose tagged universities are ALL unranked (list shows in DB-arbitrary order): **{len(no_ranked)}**")
    if no_ranked:
        r.p("  " + ", ".join(no_ranked[:top]) + (" …" if len(no_ranked) > top else ""))

    # ---------------------------------------------------------------- 8. cost gaps
    r.h("8. Program cost gaps")
    no_cost = [
        (u, p) for u in unis for p in u["programs"]
        if not p.get("cost_per_year") and not p.get("cost_label")
        and not p.get("cost_per_year_min") and not p.get("cost_per_year_max")
    ]
    r.bullet(f"programs with no cost of any kind (card shows «стоимость не указана»): **{len(no_cost)}** / {total_progs}")
    cc = Counter(u.get("country") for u, _ in no_cost)
    for c, n in cc.most_common(12):
        r.bullet(f"{c or '?'}: {n}")

    # ---------------------------------------------------------------- write
    text = str(r)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(text)
    print(f"\n[report written to {args.out}]")


if __name__ == "__main__":
    main()
