# Temporal Factory

A software factory built on [Temporal](https://temporal.io): durable workflows that take a GitHub issue labeled `factory`, produce code changes, and deliver them as a merged PR on the configured repo. It is a Temporal port of [`examples/software-factory-claude-code-v2`](examples/software-factory-claude-code-v2/README.md): workflow code replaces the LLM orchestrator, and each agent is an activity running Claude via the Claude Agent SDK.

`issue` → intake → route → spec → [build → gate → review]* → approve → merge

## Docs (Obsidian vault: `features/temporal_factory/`)
- [Pipeline flow](features/temporal_factory/Pipeline%20flow.md) — flows, dispatch, shared steps, task queues; one note per flow in `Flows/`
- [Temporal setup decisions](features/temporal_factory/Temporal%20setup%20decisions.md) — server stack, worker queues, workflow and retry design
- [docker compose setup](features/temporal_factory/docker%20compose%20setup.md) — services, startup order, volumes
- [First run](features/temporal_factory/First%20run.md) — first end-to-end run (`tfiling/barav_poc` #1 → PR #2), issues fixed, observed limits
- [Known limitations](features/temporal_factory/Known%20limitations/README.md) — tech debt, gaps and limitations (e.g. PRs merged on GitHub need `factory.cli merged <issue>`)
- Feature PRDs also live in the vault.

## Run (Docker only)
Shortcuts in `scripts/` (any directory): `up.sh` (build/restart), `test.sh` (tests the working tree, no rebuild), `dry-run.sh [base]`, `cli.sh <command>`. `dry-run.sh` and `cli.sh` start the worker if it's down and warn when it is behind the working tree (or the CLI image); only builds run from `scripts/` record the version. Underlying commands:
```
cp .env.example .env        # CLAUDE_CODE_OAUTH_TOKEN (or ANTHROPIC_API_KEY), GH_TOKEN, TARGET_REPO
docker compose up -d --build
docker compose run --rm worker python -m factory.cli queue          # run every issue labeled `factory`
docker compose run --rm worker python -m factory.cli queue-status   # jobs, stages, cost
docker compose run --rm worker python -m factory.cli run <issue>    # or run a single issue
docker compose run --rm worker python -m factory.cli status <issue>  # issue commands take --flow <name> (default implement)
docker compose run --rm worker python -m factory.cli dry-run [base] [--json]   # checks on up-to-date main, throwaway worktree
docker compose run --rm worker pytest                                # tests the built image
echo "do X instead" | docker compose run --rm -T worker python -m factory.cli feedback <issue>   # also: reject (stdin); merged, replied (no text)
```
- The queue polls GitHub every 60s, caps working jobs at `concurrency`, and nudges a needs-info job when the author (or the operator) replies.
- An escalated job (`needs-human`) waits for `feedback`, `reject`, or `merged`.
- Temporal UI: http://localhost:8080. Checks run `checks_cmd` (default `bash /app/checks.sh`, which runs the target repo's npm or pytest tests); override with `FACTORY_CHECKS_CMD`.
- Job state lives in the `factory-data` volume (`/data`, clone at `/data/repo`); `docker compose down -v` deletes it.
