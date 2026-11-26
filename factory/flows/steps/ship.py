"""Approver decision, then sync with base and merge."""

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from factory.activities.agents import run_approver
    from factory.activities.merge import sync_and_merge
    from factory.core.models import AgentRequest, MergeRequest, Stage

from factory.flows.options import MERGE, agent_opts


async def approve_and_merge(wf, job, rnd: int) -> tuple[bool, str, bool]:
    """Returns (merged, why not, approved)."""
    wf.stage = Stage.APPROVE
    decision = await workflow.execute_activity(
        run_approver,
        AgentRequest(job, "approver", f"PR: #{wf.pr_number} {wf.pr_url}. Final round: {rnd}.", round=rnd),
        **agent_opts(30))
    wf.cost_usd += decision.agent.cost_usd
    if decision.decision != "APPROVE":
        return False, decision.body, False

    wf.stage = Stage.MERGING
    merge = await workflow.execute_activity(sync_and_merge, MergeRequest(job, wf.pr_number, rnd), **MERGE)
    return merge.merged, merge.detail, True
