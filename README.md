# Temporal Factory

A software factory built on [Temporal](https://temporal.io): durable workflows that take a GitHub issue labeled `factory`, produce code changes, and deliver them as a merged PR on the configured repo. It is a Temporal port of [`examples/software-factory-claude-code-v2`](examples/software-factory-claude-code-v2/README.md): workflow code replaces the LLM orchestrator, and each agent is an activity running Claude via the Claude Agent SDK.

`issue` → intake → route → spec → [build → gate → review]* → approve → merge

## Docs (Obsidian vault: `features/temporal_factory/`)
- [Pipeline flow](features/temporal_factory/Pipeline%20flow.md) — stage diagrams, reviewer routing, task queues, job artifacts
- [Temporal setup decisions](features/temporal_factory/Temporal%20setup%20decisions.md) — server stack, worker queues, workflow and retry design
- [docker compose setup](features/temporal_factory/docker%20compose%20setup.md) — services, startup order, volumes
- [First run](features/temporal_factory/First%20run.md) — first end-to-end run (`tfiling/barav_poc` #1 → PR #2), issues fixed, observed limits
- Feature PRDs, tech debt, and known limitations also live in the vault.

## Run (Docker only)
```
cp .env.example .env        # CLAUDE_CODE_OAUTH_TOKEN (or ANTHROPIC_API_KEY), GH_TOKEN, TARGET_REPO
docker compose up -d --build
docker compose run --rm worker python -m factory.cli queue          # run every issue labeled `factory`
docker compose run --rm worker python -m factory.cli queue-status   # jobs, stages, cost
docker compose run --rm worker python -m factory.cli run <issue>    # or run a single issue
docker compose run --rm worker python -m factory.cli status <issue>
docker compose run --rm worker pytest
echo "do X instead" | docker compose run --rm -T worker python -m factory.cli feedback <issue>   # also: reject, merged
```
- The queue polls GitHub every 60s, caps working jobs at `concurrency`, and nudges a needs-info job when the author replies.
- An escalated job (`needs-human`) waits for `feedback`, `reject`, or `merged`.
- Temporal UI: http://localhost:8080. The target repo needs a checks command (`FACTORY_CHECKS_CMD`, default `checks.sh`).
- Job state lives in the `factory-data` volume (`/data`, clone at `/data/repo`); `docker compose down -v` deletes it.

## Known gaps
- **Merge by hand:** The queue doesn't detect a PR merged on GitHub, so run `factory.cli merged <issue>`. See [Tech debt - Merge by hand](features/temporal_factory/Tech%20debt%20-%20Merge%20by%20hand.md).
- **Reject timing:** `reject` and `feedback` are only acted on while a job is in `needs-info` or `needs-human`.
- **Builder Stop hook:** Not ported, so the gate only runs after the builder finishes. See [Tech debt - Builder Stop hook](features/temporal_factory/Tech%20debt%20-%20Builder%20Stop%20hook.md).
- **No browser in the container:** UI/UX reviewers read the CSS and can't render pages.
- **Fixed model per role:** There's no fallback model for each role.
