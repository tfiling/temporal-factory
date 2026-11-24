---
type: known-limitation
status: accepted
created: 2026-11-23
tags: [git, docker, limitation]
related: "[[PRD - Mount target repo]]"
---

# Known limitation: worktree paths on the mounted repo

> [!note] Applies once [[PRD - Mount target repo]] is implemented. Today the repo is cloned into the `factory-data` volume at `/data/repo`.

## Limitation
Job worktrees are created inside the container at `/data/repo/.worktrees/<id>` and registered in the shared `.git` of the mounted target repo. On the host those paths don't exist, so:
- `git worktree list` on the host shows the job worktrees as stale;
- `git worktree prune` on the host would delete the metadata of live job worktrees.

The factory also edits the shared repo's branches: `cleanup_worktree` (`merge.py`) runs `git worktree remove --force` and `git branch -D <branch>` in `job.repo`. Once mounted, that deletes `factory/<id>` branches in the developer's checkout.

## Assumptions
- Per [[PRD - Mount target repo]], the host checkout may be dirty or on another branch; the factory never changes its current branch, index or working files (PRD R6). It only adds `.worktrees/`, `factory/<id>` refs and the `.git/info/exclude` entry.
- All factory changes reach `main` through side branches managed in worktrees and merged by PR.

## Decision
Accepted. The developer may keep using the host checkout, but must not run worktree commands on it while jobs are running, and must not create their own branches named `factory/*`.

**Rule:** don't run `git worktree prune` or `git worktree remove` on the host checkout while jobs are running.

## Possible future fix
Mount the repo at the same absolute path as on the host, so the registered worktree paths resolve on both sides. This needs a code change: `_ensure_repo` (`github.py`) hardcodes `data_dir()/"repo"`.
