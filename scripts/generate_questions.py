"""
OFFLINE developer tool — drafts akinator_questions bank entries via the LLM,
for a HUMAN to review before seeding.

Input is an axis code, a depth, and a kind (direct/situational) chosen by a
human — this is a lazy backfill tool: point it at whatever (axis, depth,
kind) combination is missing from the coverage log, and it drafts candidate
wording. It does NOT decide format for you: it checks the requested kind
against app.core.axes.format_for_axis(axis, depth) and flags a mismatch
instead of silently overriding your input.

NOT for the request path. This calls the LLM once per question and takes
seconds per call — never import or call this from a router/service, only run
it manually from a terminal.

It NEVER writes to the database: output is a plain JSON review file. A human
checks it (axis weights, format-rule mismatches) before seeding into
akinator_questions.

Usage (inside Docker):
    docker-compose exec api python scripts/generate_questions.py \
        --axis People --depth 0 --kind direct --count 3
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError

from app.core.axes import AXIS_CODES, format_for_axis
from app.prompts.akinator_question_gen import QUESTION_CONTENT_SCHEMA, build_messages
from app.schemas.akinator_question import AkinatorQuestionCreate
from app.services import llm_client


def check_format_rule(axis_code: str, depth: int, kind: str) -> str | None:
    """None if `kind` matches the format=f(family, depth) rule (app.core.axes.
    format_for_axis); otherwise a message explaining the mismatch. Violations
    are flagged, never silently corrected or blocked."""
    expected = format_for_axis(axis_code, depth)
    if kind == expected:
        return None
    return (
        f"format rule mismatch: axis '{axis_code}' at depth {depth} should be "
        f"'{expected}', but kind='{kind}' was requested"
    )


def _weights_to_dict(weights: list[dict]) -> dict[str, int]:
    return {w["code"]: w["value"] for w in weights}


async def generate_question(
    axis_code: str,
    depth: int,
    kind: str,
    age_variant: str,
    resolves_pair: list[str] | None,
    order: int,
) -> tuple[dict | None, list[str]]:
    """Draft one question. Returns (node, problems). node is None only if it
    fails schema validation — the problem is always reported instead of raising."""
    problems: list[str] = []
    mismatch = check_format_rule(axis_code, depth, kind)
    if mismatch:
        problems.append(mismatch)

    messages = build_messages(axis_code, depth, kind)
    content = await llm_client.complete_json(
        messages, QUESTION_CONTENT_SCHEMA, "akinator_question"
    )

    node = {
        "kind": kind,
        "depth": depth,
        "age_variant": age_variant,
        "text": content["text"],
        "text_junior": content["text_junior"],
        "options": [
            {"text": opt["text"], "axis_weights": _weights_to_dict(opt["axis_weights"])}
            for opt in content["options"]
        ],
        "resolves_pair": resolves_pair,
        "is_active": True,
        "order": order,
    }

    try:
        AkinatorQuestionCreate.model_validate(node)
    except ValidationError as exc:
        problems.append(f"schema validation failed: {exc}")
        return None, problems

    covers_target_axis = any(axis_code in opt["axis_weights"] for opt in node["options"])
    if not covers_target_axis:
        problems.append(
            f"target axis '{axis_code}' is not covered by any answer option's axis_weights"
        )

    return node, problems


async def generate_batch(
    axis_code: str,
    depth: int,
    kind: str,
    age_variant: str,
    resolves_pair: list[str] | None,
    count: int,
) -> tuple[list[dict], list[str]]:
    if axis_code not in AXIS_CODES:
        return [], [f"unknown axis code '{axis_code}' — not in AXIS_CODES"]

    nodes: list[dict] = []
    problems: list[str] = []
    for i in range(count):
        try:
            node, item_problems = await generate_question(
                axis_code, depth, kind, age_variant, resolves_pair, order=i
            )
        except llm_client.LLMError as exc:
            problems.append(f"question {i}: LLM call failed: {exc}")
            continue
        problems.extend(item_problems)
        if node is not None:
            nodes.append(node)
    return nodes, problems


async def main(
    axis_code: str,
    depth: int,
    kind: str,
    age_variant: str,
    resolves_pair: list[str] | None,
    count: int,
    out_path: Path,
) -> None:
    if not llm_client.is_enabled():
        print("LLM disabled (set LLM_ENABLED=true and LLM_API_KEY to run this tool).")
        return

    nodes, problems = await generate_batch(
        axis_code, depth, kind, age_variant, resolves_pair, count
    )

    if problems:
        print("PROBLEMS (review before seeding):")
        for problem in problems:
            print(f"  - {problem}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "axis": axis_code,
                "depth": depth,
                "kind": kind,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "questions": nodes,
                "problems": problems,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(nodes)} question(s) to {out_path}.")
    print("Review file only — nothing was written to the database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "OFFLINE question draft generator — run manually by a developer to "
            "backfill akinator_questions for a given axis/depth/kind. NEVER call "
            "this from the request path (no auth/caching/rate limiting, seconds "
            "per call). Writes a review JSON file only, never the database."
        )
    )
    parser.add_argument(
        "--axis", required=True, help="axis code, e.g. People (see app/core/axes.py)"
    )
    parser.add_argument("--depth", type=int, required=True)
    parser.add_argument("--kind", required=True, choices=["direct", "situational"])
    parser.add_argument(
        "--age-variant", default="both", choices=["both", "junior", "senior"]
    )
    parser.add_argument(
        "--resolves-pair", default=None,
        help="two profession slugs this question disambiguates, comma-separated",
    )
    parser.add_argument(
        "--count", type=int, default=1, help="how many candidate questions to draft"
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    resolved_pair = args.resolves_pair.split(",") if args.resolves_pair else None
    resolved_out = args.out or Path(
        f"scripts/question_proposals/{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    )
    asyncio.run(
        main(
            args.axis, args.depth, args.kind, args.age_variant,
            resolved_pair, args.count, resolved_out,
        )
    )
