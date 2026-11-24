---
type: known-limitation
status: accepted
created: 2026-11-23
tags: [git, docker, limitation]
related: "[[PRD - Mount target repo]]"
---

# Known limitation: worktree paths on the mounted repo

## Limitation
Job worktrees are created inside the container at `/data/repo/.worktrees/<id>` and registered in the shared `.git` of the mounted target repo. On the host those paths don't exist, so:
- `git worktree list` on the host shows the job worktrees as stale;
- `git worktree prune` on the host would delete the metadata of live job worktrees.

## Assumptions
- The mounted directory is never edited by hand. It stays on `main`.
- All changes reach `main` through side branches managed in worktrees and merged by PR.

## Decision
Accepted. Nobody uses the host checkout for development, so nobody should run worktree commands there.

**Rule:** don't run `git worktree prune` or `git worktree remove` on the host checkout while jobs are running.

## Possible future fix
Mount the repo at the same absolute path as on the host, so the registered worktree paths resolve on both sides.
