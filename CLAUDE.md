# Temporal Factory

Temporal port of the v2 software factory in `examples/software-factory-claude-code-v2/` (reference flow; its `factory/bin/job|gate|route` are ported 1:1 into `factory/`).

- Everything runs in Docker. Never run python/pip on the host.
- Tests: `docker compose run --rm worker pytest`
- Stack: `cp .env.example .env && docker compose up -d --build`; UI at :8080.
- Start a job: `docker compose run --rm worker python -m factory.cli run <issue>`

## Layout
- `factory/workflows/job.py` — JobWorkflow (stage logic; deterministic, no IO)
- `factory/activities/` — agents (Claude Agent SDK), github, git, gate
- `factory/prompts/` — agent prompts copied from the example; keep in sync with intent, not text
- `factory/config.json` — routing, models, labels, checks command

## Rules
- Activities do all IO; a gate FAIL is a return value, never an exception.
- Keep context files (this one, README) minimal.
