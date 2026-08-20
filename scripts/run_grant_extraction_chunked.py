"""Orchestrates scripts/extract_grant_scores_2026.py over the full 1656-page
document in bounded chunks, each as a SEPARATE OS process, then merges the
per-chunk JSON outputs.

Why chunked subprocesses and not one long-running process: a single-process
run of the extraction script was tried twice and both times grew unbounded
in memory (pdfplumber caches per-page parsed content and it kept climbing
past 500MB well before halfway through the document, even after calling
page.flush_cache() per page) — the second run's memory growth is what
froze the machine. Running each chunk as its own subprocess guarantees the
memory is released by the OS when that subprocess exits, regardless of what
pdfplumber does or doesn't clean up internally — no reliance on in-process
cache-clearing actually working.

Resumable: skips any chunk whose output file already exists, so a killed/
interrupted run can just be restarted.

Usage:
  python scripts/run_grant_extraction_chunked.py [--chunk-size 150] [--pdf PATH]
"""
import argparse
import json
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
CHUNK_DIR = os.path.join(_ROOT, "data", "_grant_chunks")
FINAL_OUT = os.path.join(_ROOT, "data", "grant_scores_2026_full.json")
TOTAL_PAGES = 1656


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-size", type=int, default=150)
    parser.add_argument("--pdf", default=None)
    args = parser.parse_args()

    os.makedirs(CHUNK_DIR, exist_ok=True)

    chunk_files = []
    for start in range(0, TOTAL_PAGES, args.chunk_size):
        end = min(start + args.chunk_size, TOTAL_PAGES)
        out_path = os.path.join(CHUNK_DIR, f"chunk_{start}_{end}.json")
        chunk_files.append(out_path)

        if os.path.exists(out_path):
            print(f"[skip] {start}:{end} already done", file=sys.stderr)
            continue

        cmd = [
            sys.executable,
            os.path.join(_ROOT, "extract_grant_scores_2026.py"),
            "--pages", f"{start}:{end}",
            "--out", out_path,
        ]
        if args.pdf:
            cmd += ["--pdf", args.pdf]

        print(f"[run] pages {start}:{end} ...", file=sys.stderr)
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            raise SystemExit(f"chunk {start}:{end} failed (exit {result.returncode})")
        print(f"  done: {result.stdout.strip().splitlines()[-2] if result.stdout.strip() else ''}", file=sys.stderr)

    # merge — same (specialty_code, specialty_name, quota, ovpo) group can
    # legitimately appear in two adjacent chunks if a specialty section
    # straddles the chunk boundary; recompute min/max/count across both.
    merged: dict[tuple, dict] = {}
    for path in chunk_files:
        with open(path, encoding="utf-8") as f:
            for entry in json.load(f):
                key = (entry["specialty_code"], entry["specialty_name"], entry["quota"], entry["ovpo"])
                if key not in merged:
                    merged[key] = dict(entry)
                else:
                    m = merged[key]
                    m["min_score"] = min(m["min_score"], entry["min_score"])
                    m["max_score"] = max(m["max_score"], entry["max_score"])
                    m["recipient_count"] += entry["recipient_count"]

    results = list(merged.values())
    with open(FINAL_OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nmerged groups: {len(results)}, total recipients: {sum(r['recipient_count'] for r in results)}")
    print(f"written to {FINAL_OUT}")


if __name__ == "__main__":
    main()
