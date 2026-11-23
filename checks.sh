#!/usr/bin/env bash
# Default checks, run in the job's worktree. Override with FACTORY_CHECKS_CMD.
# Exit 0 only when the branch is fit to review. Keep it fast and non-interactive.
set -euo pipefail

if [ -f package.json ]; then
  npm ci --prefer-offline
  npm test --if-present -- --run
elif [ -f pyproject.toml ] || [ -f requirements.txt ]; then
  python -m pytest -q
else
  echo "checks.sh: no known test setup in this repo; set FACTORY_CHECKS_CMD." >&2
  exit 1
fi
