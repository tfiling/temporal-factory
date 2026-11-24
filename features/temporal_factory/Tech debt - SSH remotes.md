---
type: tech-debt
status: open
created: 2026-11-23
tags: [tech-debt, git, auth]
---

# Tech debt: SSH git remotes are unsupported

## Today
The factory supports HTTPS git workflows only. In the worker container:
- `entrypoint.sh` runs `gh auth setup-git`, which makes git use `GH_TOKEN` for `https://github.com/...` remotes.
- The container has no SSH key, agent or `known_hosts`.
- The clone is `gh repo clone` (HTTPS), so this works today.

## Impact
A remote like `git@github.com:owner/repo.git` would fail on fetch and push. This matters once the target repo is mounted from a local checkout (see [[PRD - Mount target repo]]), because developers' clones often use SSH.

## Options
- Require an HTTPS `origin` and fail early in `setup_job` otherwise.
- Fetch and push through `https://github.com/$TARGET_REPO` explicitly, ignoring the configured remote.
- Mount an SSH agent socket or key into the worker (more setup, wider credential exposure).

## Status
Accepted for now. Revisit with the mount feature.
