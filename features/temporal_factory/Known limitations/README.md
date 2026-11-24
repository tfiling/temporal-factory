# Known limitations

One line per limitation. Add a line here when you add a note to this folder.

- [[Linux support]] — only macOS with Docker Desktop is tested; Linux gaps (uid/ownership, `safe.directory`, SELinux) are listed there.
- [[worktree paths on the mounted repo]] — job worktrees are registered under container paths (`/data/repo/.worktrees/...`), so host-side `git worktree prune` can delete live ones.
