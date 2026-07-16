"""
OFFLINE developer tool — drafts axis profiles (directions.profile) for taxonomy
leaves via the LLM, for a HUMAN to review before seeding.

Input is a taxonomy FILE in the shape scripts/generate_taxonomy.py writes:
{"nodes": [{"slug", "name", "parent_slug", "is_leaf"}, ...]}. Only is_leaf
nodes get a profile — intermediate categories are skipped. A node's
parent_slug is used purely as context for the LLM (resolved to the parent's
name when the parent is present in the same file); it does not need to exist
in the database.

NOT for the request path. This calls the LLM once per leaf and takes seconds
per call — never import or call this from a router/service, only run it
manually from a terminal.

It NEVER writes to the database or touches the taxonomy file: output is a
plain JSON review file, marked as a DRAFT that requires a human sign-off
before [GATE] AKN-009 lets the akinator engine read directions.profile.

Usage (inside Docker):
    docker-compose exec api python scripts/generate_profession_profiles.py \
        --in scripts/taxonomy_proposals/20260710_120000.json

Usage (locally, venv activated):
    python scripts/generate_profession_profiles.py --in <taxonomy.json> --out <profiles.json>
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.prompts.akinator_profile import (
    PROFILE_SCHEMA,
    build_messages,
    build_retry_messages,
    split_known_axes,
)
from app.services import llm_client

MAX_AXIS_RETRIES = 2  # re-asks after an unknown axis code, on top of the first attempt

SIGNOFF_NOTE = "ЧЕРНОВИК: сгенерировано ИИ батчем, требует подписи человека перед [GATE] AKN-009."


def select_leaves(nodes: list[dict]) -> list[dict]:
    """Return is_leaf nodes annotated with a `category` resolved from parent_slug
    (the parent's name if it's in this same file, else the raw parent_slug)."""
    by_slug = {node["slug"]: node for node in nodes}
    leaves = []
    for node in nodes:
        if not node.get("is_leaf"):
            continue
        parent_slug = node.get("parent_slug")
        parent = by_slug.get(parent_slug) if parent_slug else None
        category = parent["name"] if parent else parent_slug
        leaves.append({**node, "category": category})
    return leaves


async def generate_profile(leaf: dict) -> tuple[dict[str, int], list[str]]:
    """Draft one leaf's axis profile. Returns (axes, problems).

    Retries against the model when it returns axis codes outside AXIS_CODES
    (defense in depth on top of the schema's enum — see split_known_axes).
    Codes still unknown after MAX_AXIS_RETRIES are dropped, never written out,
    and reported as a problem instead."""
    messages = build_messages(leaf["name"], leaf.get("category"))
    problems: list[str] = []
    known: dict[str, int] = {}

    for attempt in range(MAX_AXIS_RETRIES + 1):
        raw = await llm_client.complete_json(messages, PROFILE_SCHEMA, "akinator_profile")
        known, unknown = split_known_axes(raw)
        if not unknown:
            break
        if attempt == MAX_AXIS_RETRIES:
            problems.append(
                f"'{leaf['slug']}': dropped unknown axis code(s) {unknown} "
                f"after {MAX_AXIS_RETRIES} retries"
            )
            break
        messages = build_retry_messages(messages, raw, unknown)

    if not known:
        problems.append(f"'{leaf['slug']}': no valid axes — needs a manual profile")
    return known, problems


async def draft_profiles(nodes: list[dict]) -> tuple[list[dict], list[str]]:
    """Draft one profile per leaf in `nodes`. Returns (profiles, problems)."""
    leaves = select_leaves(nodes)
    profiles: list[dict] = []
    problems: list[str] = []

    for leaf in leaves:
        try:
            axes, leaf_problems = await generate_profile(leaf)
        except llm_client.LLMError as exc:
            problems.append(f"'{leaf['slug']}': LLM call failed: {exc}")
            continue
        problems.extend(leaf_problems)
        profiles.append({"slug": leaf["slug"], "name": leaf["name"], "axes": axes})

    return profiles, problems


async def main(in_path: Path, out_path: Path) -> None:
    if not llm_client.is_enabled():
        print("LLM disabled (set LLM_ENABLED=true and LLM_API_KEY to run this tool).")
        return

    taxonomy = json.loads(in_path.read_text(encoding="utf-8"))
    nodes = taxonomy.get("nodes", [])
    if not nodes:
        print(f"No nodes found in {in_path}.")
        return

    profiles, problems = await draft_profiles(nodes)

    if problems:
        print("PROBLEMS (fix these during human review):")
        for problem in problems:
            print(f"  - {problem}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "draft": True,
                "note": SIGNOFF_NOTE,
                "source": str(in_path),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "profiles": profiles,
                "problems": problems,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(profiles)} draft profile(s) to {out_path}.")
    print(SIGNOFF_NOTE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "OFFLINE profile draft generator — run manually by a developer to score "
            "taxonomy leaves across the 24 akinator axes for human review. NEVER call "
            "this from the request path (no auth/caching/rate limiting, seconds per "
            "call). Writes a review JSON file only, never the database."
        )
    )
    parser.add_argument(
        "--in", dest="in_path", type=Path, required=True,
        help="taxonomy JSON file (the shape scripts/generate_taxonomy.py writes)",
    )
    parser.add_argument(
        "--out", dest="out_path", type=Path, default=None,
        help="output JSON path (default: timestamped file under scripts/profile_proposals/)",
    )
    args = parser.parse_args()

    resolved_out = args.out_path or Path(
        f"scripts/profile_proposals/{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    )
    asyncio.run(main(args.in_path, resolved_out))
