# Temporal Factory

Temporal port of the v2 software factory in `examples/software-factory-claude-code-v2/` (reference flow; its `factory/bin/job|gate|route` are ported 1:1 into `factory/`).

- Everything runs in Docker. Never run python/pip on the host.
- Tests: `docker compose run --rm worker pytest`
- Stack: `cp .env.example .env && docker compose up -d --build`; UI at :8080.
- Start a job: `docker compose run --rm worker python -m factory.cli run <issue>`

## Planning and tech debt
- Feature plans (PRDs) and tech debt live in the Obsidian vault `features/temporal_factory/` (one note per item); add or update a note there before building a feature, and record new debt there, not in context files.
- Known limitations: `features/temporal_factory/Known limitations/README.md` (index, one line each); check it before changing mounts, paths or host/OS assumptions and always make sure it is up to date with any changes you make

## Layout
- `factory/workflows/job.py` — JobWorkflow (stage logic; deterministic, no IO). Diagram: `features/temporal_factory/Pipeline flow.md` (keep it current)
- `factory/activities/` — agents (Claude Agent SDK), github, git, gate
- `factory/prompts/` — agent prompts copied from the example; keep in sync with intent, not text
- `factory/config.json` — routing, models, labels, checks command

## Rules
- Any change to the pipeline (stages, agents, activities, queues, routing, job artifacts) must update `features/temporal_factory/Pipeline flow.md` in the same change.
- Activities do all IO; a gate FAIL is a return value, never an exception.
- Keep context files (this one, README) minimal.
