"""After intake accepts: route reviewers, announce intake, create the worktree, write the spec."""

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from factory.activities.agents import run_spec_writer
    from factory.activities.git import create_worktree
    from factory.activities.github import comment_issue
    from factory.activities.routing import route_job
    from factory.core.models import AgentRequest, Comment, Stage

from factory.flows.options import GIT, agent_opts
from factory.flows.steps.intake import intake_comment


async def prepare(wf, job, intake) -> dict:
    """Returns the reviewers ({lens: model})."""
    reviewers = await workflow.execute_local_activity(
        route_job, intake, start_to_close_timeout=timedelta(seconds=10))
    await workflow.execute_activity(comment_issue, Comment(job.issue, intake_comment(intake)), **GIT)
    await workflow.execute_activity(create_worktree, job, **GIT)

    wf.stage = Stage.SPEC
    spec = await workflow.execute_activity(
        run_spec_writer, AgentRequest(job, "spec-writer", "Write spec.md."), **agent_opts(30))
    wf.cost_usd += spec.cost_usd
    return reviewers
