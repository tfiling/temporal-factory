"""Build rounds: build → gate → review, repeated until reviewed, then approve and merge.

Escalates to a human when rounds run out or something blocks; human feedback restarts the round budget.
"""

import asyncio

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from factory.activities.agents import run_builder, run_reviewer
    from factory.activities.gate import run_gate
    from factory.activities.git import verify_build
    from factory.activities.github import ensure_pr
    from factory.core.models import AgentRequest, GateRequest, Stage

from factory.flows.base import FactoryWorkflow
from factory.flows.options import GATE, GIT, agent_opts
from factory.flows.steps.human import wait_for_human
from factory.flows.steps.ship import approve_and_merge


async def build_round(wf, job, reviewers: dict, rnd: int, message: str) -> tuple[str, str, str]:
    """One build → gate → review round. Returns (kind, message, why):
    reviewed | retry (message for the next round, why if none is left) | escalate (why)."""
    wf.stage = Stage.BUILD
    build = await workflow.execute_activity(
        run_builder, AgentRequest(job, "builder", message, round=rnd, session_id=wf.session), **agent_opts(60))
    wf.cost_usd += build.agent.cost_usd
    wf.session = build.agent.session_id or wf.session
    if build.status == "BLOCKED":
        return "escalate", "", f"The builder is blocked:\n\n{build.blocked}"
    if problem := await workflow.execute_activity(verify_build, job, **GIT):
        return "escalate", "", f"The build can't be gated: {problem}"

    wf.stage = Stage.GATE
    gate = await workflow.execute_activity(run_gate, GateRequest(job, rnd), **GATE)
    if gate.verdict != "PASS":
        return ("retry",
                f"Round {rnd + 1}. The gate failed in round {rnd}: read round-{rnd}/checks.md and "
                f"checks.log in the job folder, then fix it.",
                f"The gate failed in round {rnd}, the last allowed round (see round-{rnd}/checks.md).")

    if not wf.pr_number:
        pr = await workflow.execute_activity(ensure_pr, job, **GIT)
        wf.pr_url, wf.pr_number = pr.url, pr.number

    wf.stage = Stage.REVIEW
    reviews = await asyncio.gather(*(
        workflow.execute_activity(
            run_reviewer, AgentRequest(job, f"reviewer-{lens}", f"Review round {rnd}.", round=rnd, model=model),
            **agent_opts(30))
        for lens, model in reviewers.items()))
    wf.cost_usd += sum(r.cost_usd for r in reviews)
    changes = ", ".join(r.lens for r in reviews if r.verdict == "CHANGES")
    if not changes:
        return "reviewed", "", ""
    return ("retry",
            f"Round {rnd + 1}. Reviews asked for changes: address each finding in "
            f"round-{rnd}/review-<lens>.md for {changes}.",
            f"Review rounds exhausted. Outstanding CHANGES in round-{rnd}/ from: {changes}.")

# This function never return None. Both wf.finish() and wait_for_human() return a non None value
async def build_rounds(wf: FactoryWorkflow, job, reviewers: dict, message: str = "Build the spec.") -> Stage:
    """Build rounds until merged or a human ends the job. Returns the terminal stage."""
    rnd, limit = 0, job.max_rounds
    while True:
        rnd += 1
        wf.round = rnd
        kind, next_message, why = await build_round(wf, job, reviewers, rnd, message)
        if kind == "retry" and rnd < limit:
            message = next_message
            continue

        write_decision = True
        if kind == "reviewed":
            merged, why, write_decision = await approve_and_merge(wf, job, rnd)
            if merged:
                return await wf.finish(job, Stage.MERGED)
        # else: escalate now, or a retry with no rounds left
        stage, message = await wait_for_human(wf, job, why, rnd, write_decision)
        # wait_for_human returns Stage.BUILD (the job's real status again) to mean "feedback came in,
        # build again"; any other stage is terminal. This avoids a None sentinel in a -> Stage step.
        if stage is not Stage.BUILD:
            return stage
        limit = rnd + job.max_rounds
