---
type: tech-debt
status: open
created: 2026-11-23
tags: [tech-debt, git, auth]
---

# Tech debt: SSH git remotes are unsupported

## Today
The factory supports HTTPS git workflows only. In the worker container:
- `entrypoint.sh` runs `gh auth setup-git 2>/dev/null || true` (a failure is ignored), which makes git use `GH_TOKEN` for `https://github.com/...` remotes. `GH_TOKEN` comes from `.env` through the worker's `env_file`.
- The `Dockerfile` installs `git gh nodejs npm ca-certificates bash`: no `openssh-client`, so there is no `ssh` binary at all.
- The container has no SSH key, agent or `known_hosts`.
- The clone is `gh repo clone` (HTTPS), so this works today.

## Impact
A remote like `git@github.com:owner/repo.git` would fail on fetch and push, first of all because there is no `ssh` binary, and then for lack of keys. This matters once the target repo is mounted from a local checkout (see [[PRD - Mount target repo]]), because developers' clones often use SSH.

## Options
- Require an HTTPS `origin` and fail early otherwise. The best hook is `_ensure_repo` (`github.py`), where the remote is first established, rather than only `setup_job`.
- Fetch and push through `https://github.com/$TARGET_REPO` explicitly, ignoring the configured remote. This must cover every git network call: `git.py`, `merge.py`, `human.py`, and the **builder prompt** (`factory/prompts/builder.md`: `git push -u origin <branch>`), not only the Python activities.
- Mount an SSH agent socket or key into the worker and install `openssh-client` (more setup, wider credential exposure).

## Status
Accepted for now. Revisit with the mount feature.
