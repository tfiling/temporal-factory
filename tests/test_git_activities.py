"""create_worktree against real git: worktree lives inside the clone and stays invisible to it."""

from pathlib import Path

from factory.activities.git import create_worktree
from factory.models import Job
from factory.shell import run


def test_worktree_inside_clone_is_excluded_and_idempotent(tmp_path):
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    run(["git", "init", "--bare", "-b", "main", str(origin)])
    seed = tmp_path / "seed"
    run(["git", "clone", str(origin), str(seed)])
    (seed / "a.txt").write_text("a")
    run(["git", "add", "."], cwd=seed)
    run(["git", "commit", "-m", "init"], cwd=seed)
    run(["git", "push", "origin", "HEAD:main"], cwd=seed)
    run(["git", "clone", str(origin), str(repo)])

    job = Job("001-x", 1, "x", str(tmp_path / "job"), str(repo), str(repo / ".worktrees" / "001-x"),
              "factory/001-x", "main")
    create_worktree(job)
    create_worktree(job)  # second call is a no-op

    assert (Path(job.worktree) / "a.txt").exists()
    assert run(["git", "branch", "--show-current"], cwd=job.worktree).stdout.strip() == "factory/001-x"
    assert run(["git", "status", "--porcelain"], cwd=repo).stdout.strip() == ""  # .worktrees/ is excluded
    exclude = (repo / ".git" / "info" / "exclude").read_text().splitlines()
    assert exclude.count(".worktrees/") == 1
