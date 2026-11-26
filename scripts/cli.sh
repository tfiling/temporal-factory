#!/usr/bin/env bash
# factory.cli in the worker image. Usage: scripts/cli.sh <command> (no command prints the list)
source "$(dirname "$0")/lib.sh"
factory_cli "$@"
