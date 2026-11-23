"""Git activities (ported from factory/bin/job `advance`: worktree creation and build checks)."""

from pathlib import Path

from temporalio import activity

from factory.models import Job
from factory.parsing import first_line
from factory.shell import run


def _git(job: Job, *args: str, check: bool = True):
    return run(["git", *args], cwd=job.worktree, check=check)


@activity.defn
def create_worktree(job: Job) -> None:
    """Idempotent: a fresh branch off origin/<base> in <repo>/.worktrees/<id> (git-excluded)."""
    if Path(job.worktree).exists():
        return
    exclude = Path(job.repo) / ".git" / "info" / "exclude"  # local-only ignore; nothing is committed
    current = exclude.read_text() if exclude.exists() else ""
    if ".worktrees/" not in current.splitlines():
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_text(current.rstrip("\n") + "\n.worktrees/\n")
    run(["git", "fetch", "origin", job.base], cwd=job.repo)
    Path(job.worktree).parent.mkdir(parents=True, exist_ok=True)
    has_branch = run(["git", "rev-parse", "--verify", job.branch], cwd=job.repo, check=False).returncode == 0
    cmd = ["git", "worktree", "add"] + ([job.worktree, job.branch] if has_branch else
                                        ["-b", job.branch, job.worktree, f"origin/{job.base}"])
    run(cmd, cwd=job.repo)


@activity.defn
def verify_build(job: Job) -> str:
    """Empty string when the builder left a clean, pushed branch; otherwise the problem."""
    if (status := first_line(Path(job.dir) / "build.md")) != "STATUS: READY":
        return f"build.md starts with {status!r}, not STATUS: READY"
    if _git(job, "status", "--porcelain").stdout.strip():
        return "the worktree has uncommitted changes"
    if int(_git(job, "rev-list", "--count", f"origin/{job.base}..HEAD").stdout) == 0:
        return f"{job.branch} has no commits on top of origin/{job.base}"
    _git(job, "fetch", "origin", job.branch, check=False)
    head = _git(job, "rev-parse", "HEAD").stdout.strip()
    res = _git(job, "rev-parse", f"origin/{job.branch}", check=False)
    remote = res.stdout.strip() if res.returncode == 0 else ""
    if head != remote:
        return f"{job.branch} isn't pushed: local {head[:7]}, origin {remote[:7] or 'missing'}"
    return ""
