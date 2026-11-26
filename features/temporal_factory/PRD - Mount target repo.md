---
type: prd
status: draft
created: 2026-11-23
tags: [prd, git, docker]
---

# PRD: Mount the target repo instead of cloning it

## Problem
The factory clones `TARGET_REPO` from GitHub into the `factory-data` Docker volume (`/data/repo`). That clone sits apart from the developer's local checkout (e.g. `~/code/barav_poc`), so:
- the repo is downloaded again for every new volume or stack, which is redundant;
- results can't be inspected locally until you `git fetch` in the local checkout;
- the first run failed at clone time with a 403 (observed on the first run; not verifiable from the repo), which made the clone a point of failure.

## Goal
Bind-mount the existing local checkout of the target repo at `/data/repo`. For each job the factory then:
1. runs `git fetch` on origin;
2. creates a side branch as a worktree, based on the latest `origin/main`.

## Non-goals
- Changing the branch naming (`factory/<id>`) or the worktree location (`<repo>/.worktrees/<id>`).
- Supporting more than one target repo per stack.

## Current behavior vs. requirement

| Requirement | Today | Gap |
|---|---|---|
| Repo comes from a mount | `_ensure_repo` (`factory/activities/github.py:35`) runs `gh repo clone` into `/data/repo` when `.git` is missing. `docker-compose.yml` mounts only the `factory-data` volume. | Add a bind mount and a host-path variable. Replace the clone with a check that fails clearly when no repo is mounted. |
| No clone on every run | The clone already happens once per volume, not once per job. It repeats only when the volume is new. | Small win per run. The bigger gain is reusing the local checkout and removing one network and auth step. |
| `git fetch` | `create_worktree` (`factory/activities/git.py:26`) fetches `origin <base>`, but only **after intake**. | Intake runs with `cwd=/data/repo` (`agents.py:40`) and reads whatever is checked out there. With a mount, that is the developer's working tree, which may be on another branch or dirty. Fetch in `setup_job`, and decide where intake should read (see open questions). |
| Worktree from the latest `origin/main` | Already done: `git worktree add -b factory/<id> <repo>/.worktrees/<id> origin/<base>` (`git.py:29-31`), excluded through `.git/info/exclude`. | None. The behavior stays the same. |

## Requirements
- **R1** `.env` gets a new, proposed variable (not in code yet) `TARGET_REPO_PATH=/abs/path/to/local/checkout`. `TARGET_REPO` stays the `owner/repo` value used by `gh`.
- **R2** `docker-compose.yml` mounts `${TARGET_REPO_PATH}:/data/repo`. Job state stays in the `factory-data` volume (`/data/jobs`).
- **R3** `setup_job` checks that `/data/repo/.git` exists and that the `origin` URL matches `TARGET_REPO`. Otherwise it fails with a non-retryable error. It never clones.
- **R4** `setup_job` runs `git fetch origin <base>` before intake.
- **R5** Each job's worktree branches from the fresh `origin/<base>`, as it does today.
- **R6** The factory never changes the host checkout's current branch, index or working files. It only adds `.worktrees/`, refs, and the `.git/info/exclude` entry.

## Assumptions
- The host checkout may be dirty or on another branch (see the `git fetch` row above); R6 keeps the factory from touching its branch, index or files.
- All changes reach `main` through side branches, which live in worktrees under `.worktrees/` and are merged by PR.

## Known limitations
- [[worktree paths on the mounted repo]]

## Risks and open questions
- **Auth:** if the host clone's `origin` is SSH (`git@github.com:…`), the container has no SSH key. `gh auth setup-git` only covers HTTPS. Options: require an HTTPS remote, or fetch and push through `https://github.com/$TARGET_REPO` explicitly.
- **Intake's view of the repo:** should intake read the developer's working tree, or a clean `origin/main`? A clean read option is a read-only worktree, or `git show origin/main:<path>`.
- **File ownership:** the container runs as uid 1000 (`Dockerfile`). On Linux hosts the mounted repo has to be writable by that uid. Docker Desktop on macOS handles this (observed on the first run; not verifiable from the repo).
- **Concurrent fetches:** parallel jobs that fetch the same repo can contend for ref locks. The `GIT` retry policy (5 attempts, `factory/flows/options.py:11-12`) should absorb that, but this needs confirming.
- **Shared branches:** the local branch `factory/<id>` and its cleanup (`git branch -D` in `cleanup_worktree`, `merge.py:48`) now happen in the developer's repo.

## Acceptance criteria
- With `TARGET_REPO_PATH` set, `factory.cli run <n>` makes no `gh repo clone` call, and its worktree's base commit equals `origin/main` right after the fetch.
- The job branch and worktree are visible from the host, e.g. `git -C $TARGET_REPO_PATH branch --list 'factory/*'`.
- The host checkout's current branch and `git status` are unchanged after a job.
- A missing or mismatched mount fails `setup_job` with a clear message.
- `docker compose run --rm worker pytest` passes, with tests updated for the removed clone.
