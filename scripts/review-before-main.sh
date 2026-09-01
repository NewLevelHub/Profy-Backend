#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" = "main" ]; then
  echo "Already on main — nothing to review against itself."
  exit 1
fi

# Two-stage workflow: feature branch -> PR -> dev, then dev -> PR -> main.
# On dev itself, review against main (the promotion PR). On any other
# branch, review against dev (where feature PRs actually land) — not main,
# which would include everything already sitting unreleased on dev.
if [ "$BRANCH" = "dev" ]; then
  BASE="main"
else
  BASE="dev"
fi

EFFORT="${1:-}"
PROMPT="/code-review"
if [ -n "$EFFORT" ]; then
  PROMPT="$PROMPT $EFFORT"
fi
# scripts/data/ and university-data/ are static data dumps (JSON/hardcoded
# records), not reviewable logic — they make up ~97% of a typical dev->main
# diff's line count and cost real tokens to pull into context for nothing.
# scripts/*.py at the top level (the actual seed/backfill/apply scripts) is
# real logic and must stay in scope.
PROMPT="$PROMPT

Review the diff between $BASE and the current branch ($BRANCH) — i.e. git
diff $BASE...HEAD — not any other base. Exclude scripts/data/** and
university-data/** from that diff (e.g. git diff $BASE...HEAD -- .
':!scripts/data' ':!university-data') — these are large static data dumps,
not reviewable logic. Still review everything else normally, including
scripts/*.py at the top level."

echo "Reviewing $BRANCH -> $BASE..."
claude -p "$PROMPT" --permission-mode bypassPermissions
