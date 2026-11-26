---
type: task
status: doing
created: 2026-11-26
tags: [refactor, flows, structure]
related: "[[Pipeline flow]]"
---

# Multi-flow structure

Reorganize the single `JobWorkflow` into reusable steps so several flows (issue→PR variants, PR follow-ups, CI dry run) can share them, and let the queue pick a flow by label.

## Plan
1. Move flow-agnostic modules to `factory/core/`, `factory/workflows/` → `factory/flows/`.
2. Extract `flows/options.py`, `flows/base.py` (`FactoryWorkflow`: state, signals, query, notify, finish) and `flows/steps/*` from `job.py`; `flows/implement.py` composes them. Workflow type name stays `JobWorkflow`, activity order unchanged (replay-safe).
3. `flows/registry.py` + `flows` section in `config.json`; the queue dispatches by label; `JobState` carries `workflow_id`.
4. First new flow: CI dry run (own PRD note first).
5. Quick-fix and PR follow-up flows (own PRD notes first).

Nested `CLAUDE.md` files in `factory/flows/`, `factory/flows/steps/` and `factory/activities/` document the rules.

## Notes
- 2026-11-26: steps 1–3 done. All tests pass; the one real history on the dev server (`factory-job-3`) replays against the new code. Per-flow overrides (`max_rounds`, `roles`) are not in `Flow` config yet: add them with the first flow that needs them (quick-fix). Steps 4–5 still todo.
- 2026-11-26: step 4 done: `CiDryRunWorkflow` + `setup_dry_run` + `cli dry-run`, see [[CI dry run]]. Real run against the target repo passed; worktree and branch were removed. `FactoryWorkflow.status` now includes `job_dir`. Step 5 (quick-fix, PR follow-up) todo.
- `QueueIssue.flow` is resolved in `list_queue_issues` (config is IO), defaulting to `implement` so recorded results without it replay unchanged.
