# Temporal Factory

Temporal port of the v2 software factory in `examples/software-factory-claude-code-v2/` (reference flow; its `factory/bin/job|gate|route` are ported 1:1 into `factory/`).

- Everything runs in Docker. Never run python/pip on the host.
- Tests: `scripts/test.sh` (runs the working tree; `docker compose run --rm worker pytest` tests the last built image)
- Stack: `cp .env.example .env && docker compose up -d --build`; UI at :8080.
- Start a job: `docker compose run --rm worker python -m factory.cli run <issue>`

## Planning and tech debt
- Feature plans (PRDs) live in the Obsidian vault `features/temporal_factory/` (one note per item); add or update a note there before building a feature.
- Future implementation tasks (refactors, small features) are tracked as one note each in `features/temporal_factory/Tasks/` (frontmatter `status: todo|doing|done`); create the note before starting, update its status and notes as work progresses, and mark it done when finished. Small items can go in `Tasks/Simple TODOs.md`.
- Tech debt, gaps and limitations: one note each in `features/temporal_factory/Known limitations/`, indexed one line each in its `README.md`; record new ones there, not in context files, check it before changing mounts, paths or host/OS assumptions, and keep it up to date with your changes

## Layout
- `factory/core/` — models, config, parsing, routing (no Temporal workflow code)
- `factory/activities/` — all IO, grouped by domain; see its CLAUDE.md
- `factory/flows/` — workflows composed from shared steps; see its CLAUDE.md. Diagrams: `features/temporal_factory/Pipeline flow.md` (index) and `Flows/`
- `factory/prompts/` — agent prompts copied from the example; keep in sync with intent, not text
- `scripts/` — host shortcuts for common Docker commands; shared helpers in `lib.sh`
- `factory/config.json` — routing, models, labels, checks command, flows (label → flow)

## Rules
- Any change to a flow or shared step (stages, agents, activities, queues, routing, job artifacts) must update its note in `features/temporal_factory/Flows/` and, for shared parts, `Pipeline flow.md` in the same change.
- Activities do all IO; a gate FAIL is a return value, never an exception.
- Keep context files (this one, README) minimal.
