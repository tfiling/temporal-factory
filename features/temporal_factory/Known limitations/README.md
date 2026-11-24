# Known limitations

Tech debt, gaps and limitations, one note each. One line per note here; add a line when you add a note to this folder.

## Pipeline
- [[Merge by hand]] — the queue doesn't detect a PR merged on GitHub; run `factory.cli merged <issue>`.
- [[Reject timing]] — `reject` and `feedback` are only acted on while a job is in `needs-info` or `needs-human`.
- [[Builder Stop hook]] — not ported, so the gate only runs after the builder finishes.
- [[No browser in the container]] — UI/UX reviewers read the CSS and can't render pages.
- [[Fixed model per role]] — no fallback model for each role.

## Hosts, mounts and git
- [[Linux support]] — only macOS with Docker Desktop is tested; once the target repo is bind-mounted, Linux gaps (uid/ownership, `safe.directory`, SELinux, worktree paths) apply.
- [[worktree paths on the mounted repo]] — once the target repo is bind-mounted, job worktrees are registered under container paths (`/data/repo/.worktrees/...`), so host-side `git worktree prune` can delete live ones, and `cleanup_worktree` deletes `factory/*` branches in the host checkout.
- [[SSH git remotes]] — the worker has no `ssh` binary or keys, so an SSH `origin` (`git@github.com:...`) fails on fetch and push; HTTPS only until the mount feature lands.
