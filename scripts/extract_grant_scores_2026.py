"""Extracts every (specialty, quota, ОВПО) group's min/max grant score from
the full 1656-page "СПИСОК ОБЛАДАТЕЛЕЙ ОБРАЗОВАТЕЛЬНЫХ ГРАНТОВ НА 2026-2027
УЧЕБНЫЙ ГОД" PDF, using pdfplumber (a Python library) rather than reading the
PDF through the chat tool — the previous session found that reading this PDF
page-by-page through the chat's own PDF reader makes the session hang, but
running a library-based extraction script does not touch that path at all.

Structure of the source document (verified by sampling pages 0, 1, 2, 100,
800, 1655): each specialty section starts with a plain-text heading like
"B001 - Педагогика и психология", contains one or more quota subsections
("ОБЩИЙ КОНКУРС", "СЕЛЬСКАЯ КВОТА", ...), and under each quota a table of
individual grant recipients: № | ИКТ | ФИО | Сумма баллов | ОВПО, sorted
descending by score. The lowest score in a (specialty, quota, ОВПО) group is
the real 2026-2027 passing score for that group — same quantity
scripts/apply_grant_admission_data_2026.py already writes into
Program.requirements["admission_scores_2026"] for the 517 programs matched
so far, from a manually-produced version of this same extraction
(scripts/data/db_updates_2026.json).

This script only extracts and aggregates — it does NOT touch the database.
Output: scripts/data/grant_scores_2026_full.json, a list of
  {"specialty_code": "B001", "specialty_name": "...", "quota": "...",
   "ovpo": "013", "min_score": 100, "max_score": 130, "year": "2026-2027",
   "recipient_count": 7}
grouped and ready for a separate matching step (matching specialty_name to
our Program rows is a different, harder problem — see
docs/university-module-fix-plan.md A2 — this script only produces the raw
aggregated facts).

Run with plain Python (pdfplumber is a host dependency, not necessarily
inside the api container):
  python scripts/extract_grant_scores_2026.py [--pages START:END] [--pdf PATH]

Takes several minutes for the full document — prints progress every 100
pages. Safe to interrupt and resume by narrowing --pages, since it doesn't
write to the DB.
"""
import argparse
import gc
import json
import re
import sys

import pdfplumber

SPECIALTY_HEADING_RE = re.compile(r"^([AB]\d{3})\s*[-–]\s*(.+)$")
QUOTA_HEADING_RE = re.compile(
    r"^(ОБЩИЙ КОНКУРС|СЕЛЬСКАЯ КВОТА|КВОТА ДЛЯ ЛИЦ.*|ЦЕЛЕВАЯ КВОТА.*|.*КВОТА.*)$"
)
DEFAULT_PDF = (
    r"C:/Users/amanz/AppData/Local/Temp/claude/c--Users-amanz-OneDrive-Desktop-ProfOr/"
    r"4e427020-08bb-4d7e-9c47-95562310defa/scratchpad/grants_2026_2027.pdf"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", default=DEFAULT_PDF)
    parser.add_argument("--pages", default=None, help="START:END, 0-indexed, END exclusive")
    parser.add_argument("--out", default="scripts/data/grant_scores_2026_full.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start, end = 0, None
    if args.pages:
        s, e = args.pages.split(":")
        start, end = int(s), int(e)

    # groups: (specialty_code, specialty_name, quota, ovpo) -> list[int scores]
    groups: dict[tuple, list[int]] = {}
    current_specialty: tuple[str, str] | None = None
    current_quota = "ОБЩИЙ КОНКУРС"

    with pdfplumber.open(args.pdf) as pdf:
        stop = end if end else len(pdf.pages)
        total = stop - start
        for i in range(start, stop):
            # pdfplumber caches each page's parsed content (chars, layout,
            # images) and never frees it — indexing pdf.pages[start:end]
            # upfront (the previous version of this script) keeps all 1656
            # Page objects alive simultaneously, and memory grows without
            # bound until the machine chokes (confirmed: killed a run that
            # had reached ~1.3GB and was still climbing ~200MB/5s after
            # 1300/1656 pages). Fetching one page at a time and flushing its
            # cache immediately after keeps peak memory flat regardless of
            # document length.
            page = pdf.pages[i]
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line = line.strip()
                m = SPECIALTY_HEADING_RE.match(line)
                if m:
                    current_specialty = (m.group(1), m.group(2).strip())
                    current_quota = "ОБЩИЙ КОНКУРС"
                    continue
                if QUOTA_HEADING_RE.match(line) and len(line) < 60:
                    current_quota = line

            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 5:
                        continue
                    if row[0] and not row[0].isdigit():
                        # quota sub-header row like ['ОБЩИЙ КОНКУРС', None, None, None, None]
                        label = (row[0] or "").strip()
                        if label:
                            current_quota = label
                        continue
                    score_cell = row[3]
                    ovpo_cell = row[4]
                    if not score_cell or not ovpo_cell:
                        continue
                    score_str = re.sub(r"\D", "", score_cell)
                    ovpo_str = re.sub(r"\D", "", ovpo_cell)
                    if not score_str or not ovpo_str or current_specialty is None:
                        continue
                    key = (current_specialty[0], current_specialty[1], current_quota, ovpo_str.zfill(3))
                    groups.setdefault(key, []).append(int(score_str))

            page.flush_cache()

            done = i - start + 1
            if done % 100 == 0 or done == total:
                print(f"  ...page {i + 1} ({done}/{total})", file=sys.stderr)
                gc.collect()

    results = []
    for (code, name, quota, ovpo), scores in groups.items():
        results.append(
            {
                "specialty_code": code,
                "specialty_name": name,
                "quota": quota,
                "ovpo": ovpo,
                "min_score": min(scores),
                "max_score": max(scores),
                "year": "2026-2027",
                "recipient_count": len(scores),
            }
        )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\ngroups extracted: {len(results)}, total recipients: {sum(r['recipient_count'] for r in results)}")
    print(f"written to {args.out}")


if __name__ == "__main__":
    main()
