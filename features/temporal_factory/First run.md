---
type: log
status: current
created: 2026-11-24
tags: [run, e2e, barav_poc, walkthrough]
---

# First end-to-end run

Target `tfiling/barav_poc` (Express inventory app). Issue #1 "Add expiration date to inventory items", label `factory`. Job `factory-job-1`: **merged as PR #2 after 2 rounds, about $2.81**, issue #1 closed. Pipeline diagram: [[Pipeline flow]].

Code version: `280809d7f30478a1149f6a179963ee1b0ab9810d` (`280809d`, "Aligned docs vault"). Line references below are as of that commit and may have shifted since.

Setup: `factory.cli run 1`; gate = syntax-only checks via `FACTORY_CHECKS_CMD`; worktrees at `<data>/repo/.worktrees/<id>`, excluded through `.git/info/exclude`.

## What executed, in order

| # | Stage | Code | What happened |
|---|---|---|---|
| 0 | Start | `worker.py`, `cli.py:41` | The worker polls 3 task queues (orchestration, agents, git). `cli run 1` starts `JobWorkflow.run(1)` with ID `factory-job-1`. |
| 1 | `setup_job` | `activities/github.py:68` | `gh repo clone` into `/data/repo`. Checks issue #1 is open with the `factory` label. Creates `/data/jobs/001-add-expiration-date-to-inventory-items/` and `issue.md` (body quoted as data). Returns a `Job`: paths, branch `factory/001-…`, base `main`, `max_rounds`. |
| 2 | Intake | `agents.py:57`, `_run_agent` `agents.py:34` | Claude Agent SDK `query()` with the role prompt as system prompt, tool allowlist, model from `config.json`, `bypassPermissions`, `add_dirs=[job.dir]`. cwd is the main clone. Writes `intake.md`; the activity parses `DECISION`, `RISK`, `SURFACES`. Result: ACCEPT. |
| 3 | Route | `routing.py`, `job.py:192` | Local activity maps risk and surfaces to reviewers: base `code` (Haiku), `ui` adds `ux` (Sonnet) and `ui` (Haiku), `security` adds `security` (Opus). Four reviewers ran. |
| 4 | Worktree | `activities/git.py:17` | Adds `.worktrees/` to `.git/info/exclude`, `git fetch`, `git worktree add -b factory/001-… origin/main`. Also posted the intake comment on the issue. |
| 5 | Spec | `agents.py:73` | spec-writer runs in the worktree and writes `spec.md`. |
| 6 | Round 1 build | `agents.py:102` | Builder implements the feature and a `node:test` suite. It commits and pushes itself and writes `build.md` with `STATUS: READY`. The SDK `session_id` is kept (`job.py:120`) so later rounds resume the conversation. |
| 7 | `verify_build` | `git.py:35` | Checks READY, a clean tree, a commit ahead of `origin/main`, and local HEAD equal to the pushed HEAD. |
| 8 | Gate | `activities/gate.py:33` | Runs the checks command in the worktree and checks `protected_paths`. Writes `round-1/checks.md` and `.log`. A FAIL is a return value. Passed. |
| 9 | `ensure_pr` | `github.py:142` | Draft PR; title from `spec.md`, body `Closes #1` plus the spec Summary. Idempotent. |
| 10 | Reviews | `job.py:139` | `asyncio.gather` runs 4 `run_reviewer` activities in parallel. Each writes `round-1/review-<lens>.md` and the activity parses `VERDICT: PASS/CHANGES`. **UI: CHANGES** (3 labels shared one row in `new.html`, squeezing date inputs on phones). `_round` returns `retry` with a pointer to `review-ui.md`. |
| 11 | Round 2 | `job.py:203-228` | Builder resumes its session, fixes the layout. Gate PASS, all 4 reviews PASS. |
| 12 | Approve | `agents.py:92` | Approver writes `decision.md`, first line `APPROVE`. |
| 13 | Merge | `activities/merge.py:15` | Idempotent check of PR state, merge `origin/main` into the branch, re-run gate (`merge-checks`), push, `gh pr ready`, `gh pr merge --merge`, delete remote branch. |
| 14 | Cleanup | `merge.py:45`, `job.py:88` | `cleanup_worktree` removes the worktree and local branch. Workflow returns `merged`. |

Cost: `cost_usd` sums each agent's `ResultMessage.total_cost_usd`; read it with `factory.cli status 1`.

## Diff
5 files, +124/-8: server validation of optional `expirationDate` (YYYY-MM-DD, real date, not before `receivedDate`), date field on the form, `expires` line on inventory cards, `node:test` suite.

## Not exercised
`_wait_for_human` (needs-human, `feedback`, `reject`, `merged` signals), the NEEDS-INFO loop, and `FactoryQueueWorkflow` (the run used `cli run`, not `queue`).

## Problems found and fixed
- Worker crashed when it started before Temporal was ready. Fix: `restart: on-failure`.
- Fine-grained GitHub token lacked Contents write, so clone got 403. Fix: grant Contents read/write.
- Intake on Fable needed usage credits the subscription token lacked. Fix: intake on Opus in `factory/config.json`.
- Claude token needed re-issuing after a copy problem; a worker recreate picked up the new value.

## Observed limits
- Reviewers can't render pages (no browser in the container), so UI findings rest on reading CSS.
- Builder and reviewers can extend scope beyond the spec (the builder added a test suite although checks were syntax-only).
- Job state lives in the `factory-data` volume (`/data`); the clone is `/data/repo`. The local `~/code/barav_poc` is not used by the factory.
