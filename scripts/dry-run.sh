#!/usr/bin/env bash
# CI dry run: checks on an up-to-date base branch. Prints the report; exits 1 unless it passed.
# Usage: scripts/dry-run.sh [base]
source "$(dirname "$0")/lib.sh"
[ $# -le 1 ] || die "usage: scripts/dry-run.sh [base]"

status=0
out="$(factory_cli dry-run --json "$@")" || status=$?
echo "$out" >&2
# Parse inside the container (no jq/python assumed on the host).
report="$(docker compose exec -T worker python -c \
  'import json, sys; print(json.loads(sys.stdin.read() or "{}").get("report", ""))' <<<"$out")" || report=""
if [ -n "$report" ]; then
  docker compose exec -T worker cat "$report"
fi
exit "$status"
