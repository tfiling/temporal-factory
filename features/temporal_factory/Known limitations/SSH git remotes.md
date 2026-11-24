---
type: known-limitation
status: accepted
created: 2026-11-23
tags: [limitations, git, auth]
related: "[[PRD - Mount target repo]]"
---

# Known limitation: SSH git remotes are unsupported

> [!note] Applies once [[PRD - Mount target repo]] is implemented. Today the repo is cloned with `gh repo clone` (HTTPS) into the `factory-data` volume, so this works.

## Limitation
The factory supports HTTPS git workflows only. In the worker container:
- `entrypoint.sh` runs `gh auth setup-git 2>/dev/null || true` (failure ignored), so git uses `GH_TOKEN` for `https://github.com/...` remotes. `GH_TOKEN` comes from `.env` via the worker's `env_file`.
- The `Dockerfile` installs `git gh nodejs npm ca-certificates bash`: no `openssh-client`, so there is no `ssh` binary.
- The container has no SSH key, agent or `known_hosts`.

## Impact
A remote like `git@github.com:owner/repo.git` fails on fetch and push, first because there is no `ssh` binary, then for lack of keys. This matters once the target repo is mounted from a local checkout, because developers' clones often use SSH.

## Options
- Require an HTTPS `origin` and fail early otherwise. The best hook is `_ensure_repo` (`github.py`), where the remote is first established, rather than only `setup_job`.
- Fetch and push through `https://github.com/$TARGET_REPO` explicitly, ignoring the configured remote. This must cover every git network call: `git.py`, `merge.py`, `human.py`, and the builder prompt (`factory/prompts/builder.md`: `git push -u origin <branch>`), not only the Python activities.
- Mount an SSH agent socket or key into the worker and install `openssh-client`. More setup, and wider credential exposure.

## Decision
Accepted for now. Revisit with the mount feature.

**Rule:** until this is addressed, the target repo's `origin` must be HTTPS.
