"""
Build scripts/data/world_rank.json — the committed, portable-keyed WORLD
ranking data for universities.

ONE ranking system only: UNIRANKS Global Rank. Rationale — it is the only
source with broad enough coverage of this catalogue to work as a single
comparable sort key (1355 of 2505 universities vs 59 for QS World). Mixing
"QS for the famous ones, UNIRANKS for the rest" would put incomparable scales
in one column. QS numbers and national / KZ / subject-specific rankings are
deliberately NOT included.

Inputs (all committed, no DB, no network):
  - scripts/data/uniranks_world_rank_review.json  — 1364 `confirmed: true`
    UNIRANKS Global Rank entries. Keyed only by a dead per-DB `university_id`
    (PRO-245), so this script re-resolves each by normalised
    (our_name, country, city) against the snapshot to recover a portable key.
  - scripts/data/university_snapshot.clean.json   — the portable keys
    (slug / ror_id / jinaq_id) every entry is re-keyed to.
  - scripts/data/university_snapshot.json (raw)   — read only to REPORT how
    many universities also had a QS World number (not written to output).

Two output modes:
  (default)  scripts/data/world_rank.json  — [{ key, world_rank }], a
             standalone review artifact.
  --into P   stamp `world_rank` directly onto every matching university in
             the snapshot JSON at P (default: university_snapshot.clean.json)
             and write it back. This is the real pipeline mode — it keeps the
             catalogue as ONE self-contained file, no world_rank.json for the
             loader to also read.

Either way, scripts/data/world_rank_build_report.md records what matched.
`world_rank` -> University.ranking at load time; uniranks_kz_rank is never
touched, QS numbers and national/subject rankings are dropped.

Run (plain python on the host):
  python scripts/build_world_rank_map.py --into scripts/data/university_snapshot.clean.json
"""
import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
REVIEW = os.path.join(_DIR, "uniranks_world_rank_review.json")
CLEAN = os.path.join(_DIR, "university_snapshot.clean.json")
RAW = os.path.join(_DIR, "university_snapshot.json")
OUT = os.path.join(_DIR, "world_rank.json")
REPORT = os.path.join(_DIR, "world_rank_build_report.md")

_WS = re.compile(r"\s+")

# review `our_name` -> snapshot `name`, for the handful the merge/normalize pass
# renamed. Same hand-checked-alias discipline as every other name-match pass in
# this repo (never fuzzy). Left OUT on purpose: sub-faculties that are not their
# own university (e.g. "University of Toronto, Temerty Faculty of Medicine").
_NAME_ALIASES = {
    "nanyang technological university": "Nanyang Technological University (NTU)",
}


def norm(s):
    return _WS.sub(" ", (s or "").strip().lower())


def alias(name):
    return _NAME_ALIASES.get(norm(name), name)


def build_index(universities):
    """(name,country,city) -> [uni]  and  (name,country) -> [uni].
    Indexes each university under its `name` AND every entry in `aliases`
    (pass-2 of normalize puts the dropped English name there), so a review
    row written against the old English name still resolves to the merged
    Russian-named keeper."""
    ncc = defaultdict(list)
    nc = defaultdict(list)
    for u in universities:
        names = {u["name"], *(u.get("aliases") or [])}
        for nm in names:
            ncc[(norm(nm), norm(u.get("country")), norm(u.get("city")))].append(u)
            nc[(norm(nm), norm(u.get("country")))].append(u)
    return ncc, nc


def lookup(ncc, nc, name, country, city):
    """Exact (name,country,city), then (name,country). Returns (uni, how) or (None, why)."""
    k3 = (norm(name), norm(country), norm(city))
    if len(ncc.get(k3, [])) == 1:
        return ncc[k3][0], "name+country+city"
    k2 = (norm(name), norm(country))
    if len(nc.get(k2, [])) == 1:
        return nc[k2][0], "name+country"
    if ncc.get(k3) or nc.get(k2):
        return None, "ambiguous"
    return None, "no match"


def key_of(u):
    """Portable identity block for a snapshot university, plus name/country/city
    as human-readable anchors (the loader resolves on slug/ror_id/jinaq_id)."""
    k = {kk: vv for kk, vv in (u.get("keys") or {}).items() if vv}
    return {**k, "name": u["name"], "country": u.get("country"), "city": u.get("city")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", default=REVIEW)
    ap.add_argument("--clean", default=CLEAN)
    ap.add_argument("--raw", default=RAW)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--report", default=REPORT)
    ap.add_argument("--into", default=None,
                    help="snapshot JSON to stamp `world_rank` onto in place (pipeline mode; "
                         "no standalone world_rank.json is written)")
    ap.add_argument("--indent", type=int, default=2)
    args = ap.parse_args()

    review = json.load(open(args.review, encoding="utf-8"))
    snapshot_path = args.into or args.clean
    with open(snapshot_path, encoding="utf-8") as f:
        snapshot = json.load(f)
    clean = snapshot["universities"]
    raw = json.load(open(args.raw, encoding="utf-8"))["universities"]

    ncc, nc = build_index(clean)

    # id() of a clean-snapshot uni dict -> accumulating rank record
    acc: dict[int, dict] = {}
    uni_by_pyid = {id(u): u for u in clean}

    def touch(u):
        return acc.setdefault(id(u), {"key": key_of(u), "world_rank": None, "_matched_by": set()})

    # --- UNIRANKS Global Rank, from the confirmed review file --------------------
    conf = [e for e in review if e.get("confirmed") is True and e.get("world_rank") is not None]
    uni_matched = uni_amb = uni_missing = 0
    unmatched_rows = []
    for e in conf:
        u, how = lookup(ncc, nc, alias(e["our_name"]), e.get("country"), e.get("city"))
        if u is None:
            if how == "ambiguous":
                uni_amb += 1
            else:
                uni_missing += 1
            unmatched_rows.append(f'{e["our_name"]} [{e.get("city")}, {e.get("country")}] — {how} (world_rank {e["world_rank"]})')
            continue
        rec = touch(u)
        # Several review rows (e.g. a university and its named faculties) can
        # resolve to one snapshot university — keep the best (lowest) rank
        # so the result doesn't depend on file order.
        val = int(e["world_rank"])
        if rec["world_rank"] is None or val < rec["world_rank"]:
            rec["world_rank"] = val
        rec["_matched_by"].add(how)
        uni_matched += 1

    # QS World ints — reported only, NOT written (single-system decision).
    qs_count = sum(1 for ru in raw if ru.get("ranking") is not None)

    ranks = []
    for rec in acc.values():
        rec.pop("_matched_by", None)
        ranks.append(rec)
    ranks.sort(key=lambda r: (r["world_rank"] if r["world_rank"] is not None else 10**9,
                              r["key"]["name"]))

    counts = {"universities": len(ranks),
              "with_world_rank": sum(1 for r in ranks if r["world_rank"] is not None)}

    if args.into:
        # Pipeline mode: bake `world_rank` onto every university in the
        # snapshot (None where uniranks doesn't rate it) and write the whole
        # file back — no standalone world_rank.json.
        rank_by_pyid = {pyid: rec["world_rank"] for pyid, rec in acc.items()}
        for u in clean:
            u["world_rank"] = rank_by_pyid.get(id(u))
        snapshot.setdefault("_meta", {})["world_rank"] = {
            "system": "UNIRANKS Global Rank (single-system; QS and national/subject rankings dropped)",
            "stamped": datetime.now(timezone.utc).isoformat(),
            **counts,
        }
        with open(args.into, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=args.indent or None)
            f.write("\n")
        out_desc = f"stamped world_rank onto {counts['with_world_rank']} universities in {args.into}"
    else:
        payload = {
            "_meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "uniranks_world_rank_review.json (confirmed)",
                "note": "UNIRANKS Global Rank only (single-system). world_rank -> University.ranking. "
                        "Never uniranks_kz_rank, never a QS number.",
                "counts": counts,
            },
            "ranks": ranks,
        }
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=args.indent or None)
            f.write("\n")
        out_desc = f"world_rank.json -> {args.out}"

    r = io.StringIO()
    w = lambda s="": r.write(s + "\n")
    w("# world rank — build report\n")
    w(f"Output: {out_desc}\n")
    w("## UNIRANKS Global Rank (from confirmed review entries)\n")
    w(f"- confirmed entries with a world_rank: **{len(conf)}**")
    w(f"- matched to a snapshot university: **{uni_matched}**")
    w(f"- ambiguous (>1 candidate): {uni_amb}")
    w(f"- unmatched: {uni_missing}")
    if unmatched_rows:
        w("\n  unmatched:")
        for x in unmatched_rows:
            w(f"  - {x}")
    w(f"\n## QS World (reported only, NOT written)\n")
    w(f"- universities in the raw snapshot with a QS int: {qs_count} — dropped, single-system decision.")
    w("\n## Result\n")
    w(f"- universities carrying a UNIRANKS Global Rank: **{counts['with_world_rank']}**")
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(r.getvalue())

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(r.getvalue())
    print(f"[{out_desc}]")
    print(f"[report -> {args.report}]")


if __name__ == "__main__":
    main()
