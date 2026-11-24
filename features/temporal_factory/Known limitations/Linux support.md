---
type: limitations
status: living
created: 2026-11-23
tags: [limitations, linux, macos]
---

# Known limitations: Linux

> [!note] Applies once [[PRD - Mount target repo]] is implemented. Today the repo is cloned into the `factory-data` volume at `/data/repo`.

The factory is developed and tested on **macOS with Docker Desktop**. Linux hosts are not tested. This page lists the gaps that could stop the factory running on Linux once the target repo is bind-mounted. Add a row whenever one is found.

| # | Gap | Why it matters on Linux | Workaround / fix | Status |
|---|---|---|---|---|
| 1 | **File ownership of the mounted target repo** | The worker runs as uid 1000 (`Dockerfile:9`: `useradd -m -u 1000 factory`). Docker Desktop on macOS maps bind-mount ownership, so this works there. On Linux, bind mounts keep the host's uid/gid. If your user isn't uid 1000, the container can't write to the repo (worktree, `.git/info/exclude`, refs). See [[PRD - Mount target repo]]. | Build the image with the host's uid (`--build-arg UID=$(id -u)`), which first needs an `ARG UID` in the `Dockerfile` (there is none today), or run the worker with `user: "${UID}:${GID}"`. Neither is implemented. | Open |
| 2 | **git "dubious ownership"** | If the mounted repo's owner differs from the container user, git refuses to operate on it (`safe.directory`). | Add `git config --global --add safe.directory /data/repo` to `entrypoint.sh`. | Open |
| 3 | **Host-side files owned by the container user** | Worktrees, branches and `.git` objects created by the worker may be owned by another uid on the host, so host git commands can fail on them. | Same fix as #1: match uid/gid. | Open |
| 4 | **Worktree paths registered under container paths** | See [[worktree paths on the mounted repo]]. The risk is host-side (`git worktree prune` on the host); the factory itself only runs `git worktree remove --force` (`merge.py`, `cleanup_worktree`). Not Linux-specific, but a Linux bind mount can't hide it. | See the linked note. | Open |
| 5 | **SELinux hosts (Fedora, RHEL)** | Bind mounts are blocked unless labeled. | Add `:z` to the `${TARGET_REPO_PATH}:/data/repo` mount once the PRD adds it (no bind mount exists in `docker-compose.yml` today). | Open |

## Notes
- Gap #1 was raised while writing [[PRD - Mount target repo]].
- Until these are addressed, the factory works as documented only on macOS with Docker Desktop. The Linux fixes above are suggestions and are untested.
