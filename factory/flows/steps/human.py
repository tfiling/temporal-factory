"""Escalate to a human and wait for feedback, a rejection or a merge by hand."""

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from factory.activities.github import edit_labels
    from factory.activities.human import escalate_job, reject_job, write_feedback
    from factory.core.models import EscalateArgs, LabelChange, LabelKind, Stage, TextArgs

from factory.flows.options import GIT


async def wait_for_human(wf, job, why: str, rnd: int, write_decision: bool = True) -> tuple[Stage, str]:
    """Returns (terminal stage, "") or (Stage.BUILD, message for the next build round)."""
    await workflow.execute_activity(escalate_job, EscalateArgs(job, why, wf.pr_number, write_decision), **GIT)
    wf.stage, wf.waits = Stage.NEEDS_HUMAN, wf.waits + 1
    await wf.notify()
    await workflow.wait_condition(lambda: bool(wf.feedback) or wf.rejection is not None or wf.merged)
    if wf.merged:
        await workflow.execute_activity(edit_labels, LabelChange(job.issue, remove=[LabelKind.NEEDS_HUMAN]), **GIT)
        return await wf.finish(job, Stage.MERGED), ""
    if wf.rejection is not None:
        await workflow.execute_activity(reject_job, TextArgs(job, wf.rejection, wf.pr_number), **GIT)
        return await wf.finish(job, Stage.REJECTED), ""
    wf.stage = Stage.BUILD
    await wf.notify()
    text, wf.feedback = "\n\n".join(wf.feedback), []
    k = await workflow.execute_activity(write_feedback, TextArgs(job, text), **GIT)
    return Stage.BUILD, (f"Round {rnd + 1}. The job escalated and a human sent feedback: read feedback-{k}.md, "
                  f"decision.md and every round folder first.")
