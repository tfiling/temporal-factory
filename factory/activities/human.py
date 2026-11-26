"""Escalation, feedback and rejection (ported from `escalate`, `cmd_feedback`, `cmd_reject` in factory/bin/job)."""

import json
from pathlib import Path

from temporalio import activity

from factory.activities.github import MARKER, current_user, gh
from factory.core.config import load_config
from factory.core.models import EscalateArgs, TextArgs
from factory.core.shell import run


def _comment(number: int, kind: str, body: str) -> None:
    gh(kind, "comment", str(number), "--body", f"{MARKER}\n{body}")


@activity.defn
def escalate_job(a: EscalateArgs) -> None:
    """Record decision.md, mark the PR ready, comment, and label the issue for a human."""
    if a.write_decision:
        (Path(a.job.dir) / "decision.md").write_text(f"ESCALATE\n\n## Why\n{a.why}\n")
    body = f"### Factory: needs a human\n\n{a.why}"
    if a.pr:
        if _is_draft(a.pr):
            gh("pr", "ready", str(a.pr))
        _comment(a.pr, "pr", body)
    else:
        _comment(a.job.issue, "issue", body)
    gh("issue", "edit", str(a.job.issue), "--add-label", load_config().labels.needs_human)


def _is_draft(pr: int) -> bool:
    return json.loads(gh("pr", "view", str(pr), "--json", "isDraft"))["isDraft"]


@activity.defn
def write_feedback(a: TextArgs) -> int:
    """Save a human's feedback as feedback-<k>.md, clear the needs-human label, return k."""
    d = Path(a.job.dir)
    k = len(list(d.glob("feedback-*.md"))) + 1
    path = d / f"feedback-{k}.md"
    if not path.exists():  # idempotent on retry
        path.write_text(f"# Feedback {k}\n\nFrom @{current_user()} after the job escalated.\n\n{a.text.strip()}\n")
    gh("issue", "edit", str(a.job.issue), "--remove-label", load_config().labels.needs_human)
    return k


@activity.defn
def reject_job(a: TextArgs) -> None:
    """Write rejection.md, comment, drop the labels, close the PR and delete the branch."""
    labels = load_config().labels
    (Path(a.job.dir) / "rejection.md").write_text(
        f"REJECTED\n\nBy @{current_user()} while the job was waiting.\n\n{a.text.strip()}\n")
    _comment(a.job.issue, "issue", f"### Factory: rejected\n\n{a.text.strip()}")
    gh("issue", "edit", str(a.job.issue), "--remove-label",
       f"{labels.queue},{labels.needs_info},{labels.needs_human}")
    if a.pr:
        gh("pr", "close", str(a.pr))
        run(["git", "push", "origin", "--delete", a.job.branch], cwd=a.job.repo, check=False)
