"""
Build-time orchestrator: run the whole chain that turns the raw DB dump into
the ONE committed catalogue file, scripts/data/university_snapshot.clean.json.

    1. normalize_university_snapshot.py     dedup (pass 1/2/3), strip rank+cost
    2. build_world_rank_map.py --into       stamp world_rank (UNIRANKS)
    3. canonicalize_university_slugs.py     one canonical slug per row (+ rename map)
    4. build_program_direction_map.py       (re)seed the tag map + coverage report
    5. apply_program_direction_map.py       stamp profession tags into the file

Step 0 (export_university_snapshot.py, needs the DB) is NOT run here — it is
the rare "re-snapshot from a fresh DB" step. This orchestrator only rebuilds
the clean file from the committed raw dump + the committed review/map files,
so it is safe to run any time, offline, and is deterministic.

  python scripts/build_catalog.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    ["normalize_university_snapshot.py"],
    ["build_world_rank_map.py", "--into", os.path.join(HERE, "data", "university_snapshot.clean.json")],
    ["canonicalize_university_slugs.py"],
    ["build_program_direction_map.py"],
    ["apply_program_direction_map.py"],
]


def main() -> int:
    py = sys.executable
    for i, step in enumerate(STEPS, 1):
        script = step[0]
        print(f"\n=== [{i}/{len(STEPS)}] {script} " + " ".join(step[1:]) + " ===")
        rc = subprocess.run([py, os.path.join(HERE, script), *step[1:]],
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"}).returncode
        if rc != 0:
            print(f"\n!! step {i} ({script}) failed with exit {rc} — stopping")
            return rc
    print("\n=== catalogue built: scripts/data/university_snapshot.clean.json ===")
    print("next: build_universities.py --dry-run  (then --check, then apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
