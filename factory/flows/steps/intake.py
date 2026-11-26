"""Intake: decide the issue, asking the author for info until it does."""

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from factory.activities.agents import run_intake
    from factory.activities.github import comment_issue, edit_labels, restart_intake
    from factory.activities.human import reject_job
    from factory.core.models import AgentRequest, Comment, LabelChange, LabelKind, Stage, TextArgs

from factory.flows.options import GIT, agent_opts


def intake_comment(intake_result) -> str:
    return f"### Factory intake: {intake_result.decision}\n\n{intake_result.body}"


async def intake(wf, job):
    """Run intake until it decides. Returns the IntakeResult, or None if rejected while waiting."""
    while True:  # intake repeats after each author reply
        wf.stage = Stage.INTAKE
        result = await workflow.execute_activity(
            run_intake, AgentRequest(job, "intake", "Decide this issue and write intake.md."), **agent_opts(15))
        wf.cost_usd += result.agent.cost_usd
        if result.decision != "NEEDS-INFO":
            return result
        if not await wait_for_author(wf, job, result):
            return None


async def wait_for_author(wf, job, result) -> bool:
    """Ask the author for info and wait. Returns False if the job was rejected instead."""
    await workflow.execute_activity(comment_issue, Comment(job.issue, intake_comment(result)), **GIT)
    await workflow.execute_activity(edit_labels, LabelChange(job.issue, add=[LabelKind.NEEDS_INFO]), **GIT)
    wf.stage, wf.waits = Stage.NEEDS_INFO, wf.waits + 1
    await wf.notify()
    await workflow.wait_condition(lambda: wf.replied or wf.rejection is not None)
    if wf.rejection is not None:
        await workflow.execute_activity(reject_job, TextArgs(job, wf.rejection), **GIT)
        return False
    wf.replied = False
    await workflow.execute_activity(restart_intake, job, **GIT)
    return True


async def reject_at_intake(wf, job, result) -> Stage:
    await workflow.execute_activity(comment_issue, Comment(job.issue, intake_comment(result)), **GIT)
    await workflow.execute_activity(edit_labels, LabelChange(job.issue, remove_flow_label=wf.flow), **GIT)
    wf.stage = Stage.REJECTED
    return wf.stage
