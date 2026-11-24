# Known limitations

One line per limitation. Add a line here when you add a note to this folder.

- [[Linux support]] — only macOS with Docker Desktop is tested; once the target repo is bind-mounted, Linux gaps (uid/ownership, `safe.directory`, SELinux, worktree paths) apply.
- [[worktree paths on the mounted repo]] — once the target repo is bind-mounted, job worktrees are registered under container paths (`/data/repo/.worktrees/...`), so host-side `git worktree prune` can delete live ones, and `cleanup_worktree` deletes `factory/*` branches in the host checkout.
