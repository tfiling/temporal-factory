---
type: prd
status: draft
created: 2026-11-23
tags: [prd, git, concurrency]
related: "[[PRD - Mount target repo]]"
---

# PRD: Dedicated "sync main" step with a git lock

> [!note] Applies once [[PRD - Mount target repo]] is implemented. Today the repo is cloned into the `factory-data` volume at `/data/repo`.

## Problem
With the target repo mounted ([[PRD - Mount target repo]]), intake reads the main checkout at `/data/repo`. That checkout must be a clean, current `main`, not whatever the developer left checked out. Today nothing updates it before intake: no fetch happens before intake at all. The fetches that exist (`create_worktree` `fetch origin <base>` in `git.py`, which runs after intake; `verify_build` `fetch origin <branch>` in `git.py`; `sync_and_merge` `fetch origin <base>` in `merge.py`) only update remote-tracking refs, never the local `main` branch or its files.

## Goal
Add a step early in the `implement` flow (`ImplementWorkflow`, type `JobWorkflow`), before intake, that brings the main checkout's `main` up to date with `origin/main`.

## Requirements
- **R1** New activity `sync_main` on the git queue, called right after `setup_job` and before intake. It runs `git fetch origin main` and then `git merge --ff-only origin/main` in `/data/repo`. It must be idempotent and fast-forward only.
- **R2** If the checkout isn't on a clean `main` (wrong branch, dirty, or not fast-forwardable), the step fails with a clear, non-retryable error. It never resets or discards local work. `sync_main` would run with the `GIT` profile (5 attempts, backoff ×2, `flows/options.py`), so it must raise `ApplicationError(non_retryable=True)`; otherwise it retries 5 times.
- **R3** A single lock serializes `sync_main` and `create_worktree`. Only one of them touches the main repo's `.git` at a time. The lock must work across jobs and across worker processes. Two ways to do it:
  - a Temporal lock workflow that jobs request a lease from (survives restarts and works across workers); or
  - a file lock (`flock` on `/data/repo/.git/factory.lock`) taken inside the two activities (simpler; only valid while every worker shares that filesystem).
  - Design gaps: sync activities run in threads of a shared `ThreadPoolExecutor` (`worker.py`), and workers may also be separate processes, so the file lock must be `fcntl.flock` on a file descriptor opened per call (not a process-wide lock object). A Temporal lease needs a TTL or a heartbeat to satisfy R5; neither is specified yet.
- **R4** The lock is held only for the git operation, never during agent runs, so jobs still run in parallel.
- **R5** The lock has a timeout and is released if the holder dies, so a crashed activity can't block the queue.

## Steps that could interfere
Every operation that mutates the main repo's `.git` or its checkout must take the same lock, or be shown not to conflict:

| Step | File | Interference |
|---|---|---|
| `create_worktree` (`git fetch`, then one `git worktree add [-b]`) | `git.py:17` | Races with the sync over refs and the index. **Takes the lock.** |
| `cleanup_worktree` (`worktree remove`, `branch -D`) | `merge.py:45` | Edits worktree metadata and branches while a sync runs. **Takes the lock.** |
| `sync_and_merge` (`git fetch origin <base>` from the worktree) | `merge.py:24` | Fetch updates shared refs. Retry on ref-lock errors, or take the lock. |
| `sync_and_merge` (`git push origin --delete <branch>` from the main repo) | `merge.py:40` | Remote-only; may prune a remote-tracking ref. No lock needed. |
| `verify_build` (`git fetch origin <branch>`) | `git.py:43` | Same ref-lock exposure. Retry, or take the lock. |
| Builder pushes and the gate | `agents.py`, `gate.py` | Work in the job's own worktree, not the main checkout. No lock needed. |
| Intake | `agents.py:40` | **Reads** the main checkout, so it must not run during a sync. Start it only after `sync_main` finishes. A sync from another job must not move files under a running intake. |
| Developer's own git commands in the mounted repo | host | Out of the factory's control. R2 makes the sync fail safely. Document that the mounted checkout should stay on a clean `main`. |

## Open questions
- Should intake read from a read-only worktree of `origin/main` instead? That removes the intake interference above and makes this lock matter only for ref updates.
- Lock choice: Temporal lock workflow vs. file lock.

## Acceptance criteria
- Two jobs started together never run `sync_main` and `create_worktree` at the same time, shown by a test with two concurrent calls.
- After `sync_main`, the local `main` equals `origin/main`.
- A dirty or off-`main` checkout fails the step with a clear message and leaves the files untouched.
- A killed lock holder doesn't block later jobs.
