---
type: architecture
status: current
created: 2026-11-24
tags: [architecture, temporal, decisions]
---

# Temporal setup decisions

The Temporal-specific choices in the factory, with where each lives in the code. Container layout is in [[docker compose setup]]. Stage logic is in [[Pipeline flow]].

## Server (`docker-compose.yml`)

| Decision                                                                                                                   | Where                                                                       | Why                                                                                                                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `temporalio/server:1.32.2` with separate one-shot `temporal-schema` and `temporal-namespace` jobs, instead of `auto-setup` | `temporal-schema`, `temporal-namespace` services                            | Per the first run, `auto-setup` was treated as deprecated (not verifiable from the repo). Schema setup and namespace creation are explicit, idempotent steps.                                                                                                          |
| Postgres for persistence **and** visibility, no Elasticsearch                                                              | `DB=postgres12` (env on `temporal`, the SQL plugin name) plus `--plugin postgres12` and the `v12` schema dir in `temporal-schema`; the database is `postgres:19`              | One database is enough for a single-host dev stack. SQL visibility needs Postgres 12 or later; `postgres12` is only the plugin name. We run `postgres:19`.                                                                                                     |
| Health-gated startup chain: postgres → schema → server → (UI) and namespace → worker                                           | `depends_on` conditions                                                     | Observed on the first run (not verifiable from the repo): the worker crashed when it started before Temporal was ready. The UI depends only on `temporal` being healthy.                                                                                                                          |
| Single `default` namespace                                                                                                 | `temporal-namespace`; clients connect without a namespace                   | No multi-tenant need yet.                                                                                                                                                                                |
| Dynamic config file `temporal/dynamicconfig/development.yaml`                                                              | mounted at `/etc/temporal/config/dynamicconfig`, `DYNAMIC_CONFIG_FILE_PATH` | Lets server knobs be set without rebuilding.                                                                                                                                                             |
| `system.forceSearchAttributesCacheRefreshOnRead: true`                                                                     | `development.yaml`                                                          | New custom search attributes become visible right away instead of after the cache refreshes (dev-only setting). The code doesn't register or upsert any search attributes yet, so this is precautionary. |
| `BIND_ON_IP=0.0.0.0`, port 7233 published                                                                                  | `temporal` service                                                          | Lets the worker container and host tools reach the frontend.                                                                                                                                             |
| Pinned UI `temporalio/ui:2.58.1`                                                                                           | `temporal-ui`                                                               | Per the first run (not verifiable from the repo), version `2.31.2` rendered blank in Chrome because its CSP blocked its own scripts.                                                                                                                       |

## Worker (`factory/worker.py`)

| Decision | Where | Why |
|---|---|---|
| Three task queues: `factory-orchestration`, `factory-agents`, `factory-git` | `factory/models.py:3-5`, `worker.py:17-29` | Long Claude agent calls (up to 60 min) don't compete with quick git/GitHub calls, and the queues can be scaled separately later. |
| All three workers in one process | `worker.py` | Simplest deploy. Splitting them is just separate containers on the same queues. |
| Sync activities run on a shared `ThreadPoolExecutor(16)`; agent activities are `async` | `worker.py:16`, `activities/agents.py` | git/gh calls are blocking subprocesses. The Agent SDK is async and streams. |
| Workflow imports through `workflow.unsafe.imports_passed_through()` | `workflows/job.py:15`, `queue.py:15` | Keeps the sandbox from re-importing activity modules (subprocess, SDK) on every replay. |

## Workflows

| Decision | Where | Why |
|---|---|---|
| One `JobWorkflow` per issue, ID `factory-job-<issue>` | `cli.py`, `queue.py:job_id` | A deterministic ID addresses the job from the CLI (signals/queries) and prevents **concurrent** duplicate runs for one issue. The CLI sets no ID reuse policy (`cli.py`), so a finished issue can be rerun from the CLI; only the queue guards reruns (`ALLOW_DUPLICATE_FAILED_ONLY`). |
| Workflow code is pure stage logic; all IO in activities | `job.py` (CLAUDE.md rule) | Keeps replay deterministic. |
| Expected failures are return values, not exceptions (gate FAIL, merge conflict, BLOCKED build, unverifiable build) | `gate.py`, `merge.py`; BLOCKED comes from `run_builder` status (`job.py`); `verify_build` returns a problem string | Temporal retries exceptions. A failed gate is a normal outcome that the workflow should route on, not retry. |
| Malformed agent output raises `ApplicationError(non_retryable=True)` | `activities/agents.py` | Rerunning the same prompt rarely fixes a broken contract and it costs money. Fail fast and visibly. |
| Human interaction through signals (`author_replied`, `human_feedback`, `reject`, `pr_merged`) plus `wait_condition` | `job.py:61-76` (signals), `100`, `180` (`wait_condition`) | A job can wait durably for days without holding a worker. |
| Progress exposed through a `status` query, not activity output | `job.py:56-59`, `queue.py` `status` | `factory.cli status` / `queue-status` read live state without touching history. |
| Builder session ID kept in workflow state and passed back on retry rounds | `job.py:119` (passed), `121` (stored) | Round N+1 resumes the same Claude conversation (`resume=`). |
| `route_job` is a **local** activity | `job.py:193-194`; 10 s start-to-close, no retry policy | Pure config lookup, so a full task-queue round-trip isn't worth it. |

## Queue (`factory/workflows/queue.py`)

| Decision | Where | Why |
|---|---|---|
| Singleton `FactoryQueueWorkflow` (ID `factory-queue`) polling GitHub every 60s | `queue.py`, `QueueInput.poll_seconds` | Per the module docstring, a port of v2's `cmd_queue` (not checked against the example here). A `poke` signal skips the wait. |
| Jobs are child workflows with `ParentClosePolicy.ABANDON` | `queue.py` `start_child_workflow` | Restarting or terminating the queue doesn't kill running jobs. |
| `WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY` | same | A failed job can be retried by the queue. Merged or rejected issues aren't rerun. |
| Jobs report state back with a `job_state` signal; the queue keeps no child handles | `job.py:_notify`, `queue.py:job_state` | The queue's state stays small and serializable, so it survives `continue_as_new`. |
| `continue_as_new` when `is_continue_as_new_suggested()` | `queue.py` | Keeps the endlessly polling queue's history bounded. |
| Concurrency counts only working jobs; `needs-info` and `needs-human` don't hold a slot | `queue.py:_working` | Jobs waiting on people don't block new work. |

## Timeouts and retries (`job.py:27-37`)

| Profile | Timeout | Max attempts | Used for |
|---|---|---|---|
| `GIT` | 5 min start-to-close | 5, backoff ×2 | clone, labels, comments, PR, worktree, escalation |
| `GATE` | 30 min | 2 | `run_gate` (checks command) |
| `MERGE` | 45 min | 2 | `sync_and_merge`. Idempotent: checks whether the PR is already merged first. |
| `agent(n)` | n min (intake 15, spec/review/approve 30, builder 60), **heartbeat 3 min** | 2 | Claude agents. The activity heartbeats on every SDK message, so a hung agent is detected within 3 min. Caveat: heartbeats are sent per SDK message (`agents.py`), so a long silent tool call (e.g. the builder running checks for over 3 min) also trips the timeout. |
| `route_job` (local) | 10 s start-to-close | default (no retry policy set) | `route_job` (`job.py:193-194`) |
| `list_queue_issues` | 2 min | 5, backoff ×2 | queue polling (`queue.py`) |

Activities that can retry are written to be idempotent: `ensure_pr` returns the existing PR, `create_worktree` skips an existing one, `restart_intake` archives only once, and `sync_and_merge` checks the merge state first.

## Open questions
- No custom search attributes yet (e.g. `Issue`, `Stage`). They would make the UI filterable and would be the reason for the cache-refresh flag.
- No worker versioning or patching strategy. Changing `job.py` while jobs are waiting in `needs-human` can break replay.
