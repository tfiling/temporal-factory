# Temporal Factory

A software factory built on [Temporal](https://temporal.io): durable workflows that take a task, produce code changes, and deliver them as pull requests to a configured GitHub repository.

## Goals
- **Automated delivery** — triggered automatically (no human in the loop to start work) and ends with a PR on the target repo.
- **Robust infra** — Temporal provides durability, retries, and visibility for long-running, multi-step work.
- **Codebase-agnostic** — a general factory that can be pointed at any repository. This may be revisited later in favor of specialization.

## Approach
Built iteratively: each iteration adds a new feature or improves an existing one. The flow is a Temporal port of the agentic pipeline in [`examples/software-factory-claude-code-v2`](examples/software-factory-claude-code-v2/README.md): the workflow code replaces the LLM orchestrator, and each agent is an activity that runs Claude via the Claude Agent SDK.

## Flow
Diagrams: `features/temporal_factory/Pipeline flow.md` (update it whenever the flow changes).

`issue (label: factory)` → intake → route → spec → [build → gate → review]* → approve → merge

| Step | Implementation |
|---|---|
| intake, spec, build | agent activities (`factory/activities/agents.py`, prompts in `factory/prompts/`) |
| route, gate, git, GitHub | deterministic activities |
| stage and round logic | `JobWorkflow` (`factory/workflows/job.py`) |

## Planning
Features are planned as PRDs in an Obsidian vault: open `features/temporal_factory/` in Obsidian (one note per feature).

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
The queue polls GitHub every 60s, caps working jobs at `concurrency`, and nudges a needs-info job when the author replies. When a job escalates (`needs-human`), it waits for `feedback` (back to the builder, round budget resets), `reject`, or `merged` (you merged the PR by hand).
Temporal UI: http://localhost:8080. The target repo needs a `factory` label on the issue and a checks command (`FACTORY_CHECKS_CMD`, default `checks.sh`).

## First end-to-end run

Target: `tfiling/barav_poc` (Express inventory app). Issue #1, "Add expiration date to inventory items", labeled `factory`.

| Job | Result |
|---|---|
| `factory-job-1` | Merged as PR #2 after 2 rounds, cost about $2.81. Issue #1 closed. |

- **Round 1:** the builder implemented the feature and added a `node:test` suite. The gate passed and the draft PR opened. The UI reviewer requested changes: the three labels shared one row in `new.html`, which would squeeze the date inputs on phones.
- **Round 2:** the builder fixed the layout, all four reviews (code, security, ui, ux) passed, and the approver approved. The factory synced with `main`, re-ran the gate and merged.
- **Diff:** 5 files, +124/−8. Server validation of optional `expirationDate` (YYYY-MM-DD, real calendar date, not before `receivedDate`), a date field on the form, an `expires` line on inventory cards, and a `node:test` suite.

### Issues found and fixed along the way
- Worker crashed when it started before Temporal was ready. Added `restart: on-failure`.
- Fine-grained GitHub token lacked Contents write, so clone failed with 403. Fixed by granting Contents read/write.
- Intake on the Fable model needed usage credits the subscription token didn't have. Intake now runs on Opus (`factory/config.json`).
- Claude token needed to be re-issued after a copy problem; the stack picked up the new value after a worker recreate.

### Observed limits
- Reviewers can't render pages: no browser in the container, so UI findings rely on reading the CSS.
- Reviewers and the builder can extend scope beyond the spec (the builder added a test suite; syntax-only checks were chosen).
- Job state lives in `/data` inside the `factory-data` volume and the clone is at `/data/repo`; the local `~/code/barav_poc` is not used by the factory.

## Known gaps
Tech debt and feature PRDs are tracked in the Obsidian vault at `features/temporal_factory/`. The entries below are first-run findings.

- **Merge by hand** — the queue doesn't detect a PR merged on GitHub; send `factory.cli merged <issue>` (v2 noticed it on its own).
When a job escalates (needs-human), it waits for a signal. If you merge the PR yourself on GitHub, nothing tells the workflow. v2's job queue checked PR state on every pass and marked the job merged. Here you have to run factory.cli merged <issue>, or the job sits in needs-human forever. The fix is to have the queue check PR state for waiting jobs, or to add a GitHub webhook.
- **Reject timing** — `reject` and `feedback` are only acted on while a job waits in `needs-info` / `needs-human`.
- **Builder Stop hook** — not ported; the gate only runs after the builder finishes.
- **Browser-based UX/UI review** — the dev-server and `agent-browser` path from v2 isn't set up in the container.
- **Model availability** — roles are hard-coded to models; Fable intake fails without usage credits, so roles should fall back or be configurable.
- **Single-job runs** — the test used `factory.cli run`; the queue path and NEEDS-INFO flow haven't been exercised end to end yet.
- **Browser tooling** — the UI reviewer said it couldn't render the pages because there's no browser in the container, so its UI findings rest on reading the CSS.
- **Reviewer judgment** — the reviewers can change the code in ways the plan didn't expect. The builder also added a test suite, though the gate was configured for syntax-only checks.
