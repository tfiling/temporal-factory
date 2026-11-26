"""Every activity by task queue. The worker registers exactly these."""

from factory.activities import agents, gate, git, github, human, merge, routing
from factory.core.models import AGENTS_QUEUE, GIT_QUEUE, ORCHESTRATION_QUEUE

ALL_BY_QUEUE = {
    ORCHESTRATION_QUEUE: [routing.route_job],  # local activities run on the workflow's worker
    AGENTS_QUEUE: [agents.run_intake, agents.run_spec_writer, agents.run_builder,
                   agents.run_reviewer, agents.run_approver],
    GIT_QUEUE: [github.setup_job, github.setup_dry_run, github.comment_issue, github.edit_labels, github.ensure_pr,
                github.list_queue_issues, github.restart_intake,
                git.create_worktree, git.verify_build, gate.run_gate,
                merge.sync_and_merge, merge.cleanup_worktree,
                human.escalate_job, human.write_feedback, human.reject_job],
}
