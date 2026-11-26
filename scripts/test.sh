#!/usr/bin/env bash
# Run the tests against the working tree (no rebuild needed). Arguments go to pytest.
source "$(dirname "$0")/lib.sh"
require_env
docker compose run --rm -T -v "$ROOT/factory:/app/factory:ro" -v "$ROOT/tests:/app/tests:ro" worker pytest "$@"
