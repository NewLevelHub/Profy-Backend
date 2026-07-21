"""
OFFLINE developer tool — proposes new akinator taxonomy nodes (professions or
intermediate categories) via the LLM, for a HUMAN to review before seeding.

NOT for the request path. This calls the LLM directly with no per-request
auth, caching or rate limiting, and takes seconds per call — never import or
call this from a router/service, only run it manually from a terminal.

It NEVER writes to the database: output is a plain JSON review file. A human
must check it (and run scripts/seed_akinator_content.py-style seeding by hand)
before any of it reaches the catalog.

Usage (inside Docker):
    docker-compose exec api python scripts/generate_taxonomy.py --focus-area "медицина" --count 8
    docker-compose run --rm api python scripts/generate_taxonomy.py --count 5
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.direction import Direction
from app.prompts.akinator_taxonomy import AKINATOR_TAXONOMY_SCHEMA, build_messages
from app.services import llm_client


def validate_nodes(nodes: list[dict], existing_slugs: set[str]) -> list[str]:
    """Problems the strict JSON schema can't express: slug uniqueness and
    parent_slug references. Empty list means the batch is safe to seed."""
    problems: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        slug = node["slug"]
        if slug in existing_slugs:
            problems.append(f"slug '{slug}' already exists in the catalog")
        if slug in seen:
            problems.append(f"slug '{slug}' is duplicated within this batch")
        seen.add(slug)

    known = existing_slugs | seen
    for node in nodes:
        parent = node["parent_slug"]
        if parent is not None and parent not in known:
            problems.append(f"node '{node['slug']}' has unknown parent_slug '{parent}'")

    # A non-leaf node with no child in this batch is a dead end — the tree
    # can't be walked past it until someone adds a profession under it.
    parents_used = {node["parent_slug"] for node in nodes if node["parent_slug"] is not None}
    for node in nodes:
        if not node["is_leaf"] and node["slug"] not in parents_used:
            problems.append(
                f"node '{node['slug']}' is_leaf=false but has no child in this batch (dead end)"
            )
    return problems


async def propose_taxonomy(
    existing_slugs: list[str], focus_area: str, count: int
) -> tuple[list[dict], list[str]]:
    """Call the LLM for one batch of candidate nodes. Returns (nodes, problems)."""
    messages = build_messages(existing_slugs, focus_area, count)
    result = await llm_client.complete_json(
        messages, AKINATOR_TAXONOMY_SCHEMA, schema_name="akinator_taxonomy"
    )
    nodes = result.get("nodes", [])
    problems = validate_nodes(nodes, set(existing_slugs))
    return nodes, problems


async def _fetch_existing_slugs() -> list[str]:
    async with async_session() as db:
        result = await db.execute(select(Direction.slug))
        return sorted(result.scalars().all())


async def main(focus_area: str, count: int, out_path: Path) -> None:
    if not llm_client.is_enabled():
        print("LLM disabled (set LLM_ENABLED=true and LLM_API_KEY to run this tool).")
        return

    existing_slugs = await _fetch_existing_slugs()
    try:
        nodes, problems = await propose_taxonomy(existing_slugs, focus_area, count)
    except llm_client.LLMError as exc:
        print(f"LLM call failed: {exc}")
        return

    if problems:
        print("VALIDATION PROBLEMS (fix these before seeding this batch):")
        for problem in problems:
            print(f"  - {problem}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "focus_area": focus_area,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "nodes": nodes,
                "problems": problems,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(nodes)} proposed node(s) to {out_path}.")
    print("Review file only — nothing was written to the database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "OFFLINE taxonomy proposal generator — run manually by a developer to "
            "draft candidate akinator tree nodes for human review. NEVER call this "
            "from the request path (no auth/caching/rate limiting, seconds per call). "
            "Writes a review JSON file only, never the database."
        )
    )
    parser.add_argument(
        "--focus-area", default="", help="e.g. 'медицина' — part of the tree to expand"
    )
    parser.add_argument(
        "--count", type=int, default=10, help="approx. number of new nodes to propose"
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="output JSON path (default: timestamped file under scripts/taxonomy_proposals/)",
    )
    args = parser.parse_args()

    resolved_out = args.out or Path(
        f"scripts/taxonomy_proposals/{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    )
    asyncio.run(main(args.focus_area, args.count, resolved_out))
