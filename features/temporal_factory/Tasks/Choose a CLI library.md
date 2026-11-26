---
type: task
status: todo
created: 2026-11-26
tags: [cli]
related: "[[Multi-flow structure]]"
---

# Choose a CLI library

## Problem
`factory/cli.py` parses arguments by hand (splices `--flow` out of argv, checks positions). Gaps: `dry-run --flow implement` (and `queue --flow ...`) silently ignore the flag (unknown or non-issue-driven names are rejected), `status <dry-run-key>` crashes on `int()`, and there's no help per command. Quick-fix and PR follow-up flows will add more commands.

## Plan
- Compare popular modern libraries (e.g. Typer, Click, cyclopts) with argparse: async commands, subcommands, typed and validated args, help output, dependency weight.
- Record the choice and why here, then port `factory/cli.py`.

## Done when
- Each command validates its own args, including `--flow` (issue-driven flows only, see [[Flow input type guard]]).
- `scripts/cli.sh` and `scripts/dry-run.sh` still work; the CLI usage in the README is updated.
