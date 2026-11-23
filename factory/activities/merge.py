"""Merge and cleanup (ported from factory/bin/job `cmd_merge` and the terminal-stage cleanup)."""

from pathlib import Path

from temporalio import activity

from factory.activities.gate import do_gate
from factory.activities.github import gh, gh_json
from factory.config import load_config
from factory.models import GateRequest, Job, MergeRequest, MergeResult
from factory.shell import run


@activity.defn
def sync_and_merge(req: MergeRequest) -> MergeResult:
    """Sync with base, re-run the gate, merge the PR. Failures are returned, not raised.

    Idempotent: an already merged PR returns merged, so a retry never merges twice.
    """
    job = req.job
    if gh_json("pr", "view", str(req.pr), "--json", "state")["state"] == "MERGED":
        return MergeResult(True)

    run(["git", "fetch", "origin", job.base], cwd=job.worktree)
    merged = run(["git", "merge", "--no-edit", f"origin/{job.base}"], cwd=job.worktree, check=False)
    if merged.returncode != 0:
        run(["git", "merge", "--abort"], cwd=job.worktree, check=False)
        return MergeResult(False, f"The branch conflicts with {job.base}:\n\n```\n{merged.stdout.strip()}\n```")

    if do_gate(GateRequest(job, req.round, merge=True)).verdict != "PASS":
        return MergeResult(False, f"The gate failed after syncing with {job.base}. "
                                  f"See round-{req.round}/merge-checks.md.")
    try:
        run(["git", "push", "origin", job.branch], cwd=job.worktree)
        if gh_json("pr", "view", str(req.pr), "--json", "isDraft")["isDraft"]:
            gh("pr", "ready", str(req.pr))
        gh("pr", "merge", str(req.pr), f"--{load_config().merge_method}")
    except RuntimeError as e:
        return MergeResult(False, f"The merge failed:\n\n```\n{e}\n```")
    run(["git", "push", "origin", "--delete", job.branch], cwd=job.repo, check=False)  # GitHub may have done it
    return MergeResult(True)


@activity.defn
def cleanup_worktree(job: Job) -> None:
    if Path(job.worktree).exists():
        run(["git", "worktree", "remove", "--force", job.worktree], cwd=job.repo, check=False)
    run(["git", "branch", "-D", job.branch], cwd=job.repo, check=False)
