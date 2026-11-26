#!/usr/bin/env bash
# Build and (re)start the stack. Run after code changes; restarting the worker interrupts running activities.
source "$(dirname "$0")/lib.sh"
require_env
docker compose up -d --build "$@"
echo "Temporal UI: http://localhost:8080"
