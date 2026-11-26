"""ImplementWorkflow (type "JobWorkflow") with mocked activities in a time-skipping Temporal test server."""

import asyncio
import uuid

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from factory.core.models import (AGENTS_QUEUE, GIT_QUEUE, ORCHESTRATION_QUEUE, AgentRequest, AgentResult,
                            BuildResult, DecisionResult, GateResult, IntakeResult, Job, LabelChange, MergeResult,
                            PrInfo, ReviewResult, Stage, FlowName)
from factory.flows.implement import ImplementWorkflow

JOB = Job("001-x", 1, "x", "/d", "/r", "/w", "factory/001-x", "main", max_rounds=3)
CALLS: list[str] = []
LABEL_CHANGES: list = []
REJECT = ("reject", "no thanks")


def make_activities(decision=("ACCEPT",), build="READY", gates=("PASS",), reviews=(("PASS",),),
                    approvals=("APPROVE",), merges=(True,)):
    """gates: verdict per round; reviews: verdicts per round (one per lens, in order code, ux);
    approvals: approver decision per call; merges: sync_and_merge outcome per call."""
    CALLS.clear()
    LABEL_CHANGES.clear()
    decisions, gates, approvals, merges = list(decision), list(gates), list(approvals), list(merges)

    def rec(name, value):
        @activity.defn(name=name)
        async def fn(_arg=None):
            CALLS.append(name)
            return value() if callable(value) else value
        return fn

    lenses = ["code", "ux"]

    @activity.defn(name="edit_labels")
    async def edit_labels(change: LabelChange) -> None:
        CALLS.append("edit_labels")
        LABEL_CHANGES.append(change)

    @activity.defn(name="run_reviewer")
    async def run_reviewer(req: AgentRequest) -> ReviewResult:
        CALLS.append("run_reviewer")
        verdicts = reviews[min(req.round, len(reviews)) - 1]
        lens = req.role.removeprefix("reviewer-")
        return ReviewResult(lens, verdicts[lenses.index(lens) % len(verdicts)], 0.5)

    def next_intake():
        d = decisions.pop(0) if len(decisions) > 1 else decisions[0]
        return IntakeResult(d, "low", [], False, "body", AgentResult(cost_usd=1.0))

    return [
        rec("setup_job", JOB), rec("run_intake", next_intake), rec("route_job", {"code": "haiku", "ux": "sonnet"}),
        rec("comment_issue", None), edit_labels, rec("create_worktree", None),
        rec("run_spec_writer", AgentResult(cost_usd=1.0)),
        rec("run_builder", BuildResult(build, "stuck" if build == "BLOCKED" else "", AgentResult("s1", 2.0))),
        rec("verify_build", ""), rec("run_gate", lambda: GateResult(gates.pop(0), "abc", 0, [])),
        rec("ensure_pr", PrInfo(7, "https://github.com/o/r/pull/7")), run_reviewer,
        rec("run_approver", lambda: DecisionResult(approvals.pop(0), "needs a look", AgentResult(cost_usd=1.0))),
        rec("sync_and_merge", lambda: MergeResult(merges.pop(0), "" if merges and merges[0] else "conflict")),
        rec("cleanup_worktree", None), rec("escalate_job", None), rec("write_feedback", 1),
        rec("reject_job", None), rec("restart_intake", None),
    ]


async def run_job(signals=(), **kw):
    """Runs a job; each (signal, arg) is sent after the job's next escalation, in order."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        acts = make_activities(**kw)
        async with (Worker(env.client, task_queue=ORCHESTRATION_QUEUE, workflows=[ImplementWorkflow], activities=acts),
                    Worker(env.client, task_queue=AGENTS_QUEUE, activities=acts),
                    Worker(env.client, task_queue=GIT_QUEUE, activities=acts)):
            handle = await env.client.start_workflow(
                ImplementWorkflow.run, 1, id=f"t-{uuid.uuid4()}", task_queue=ORCHESTRATION_QUEUE)
            for i, (name, *arg) in enumerate(signals, start=1):
                while (await handle.query(ImplementWorkflow.status))["waits"] < i:
                    await asyncio.sleep(0.05)
                await handle.signal(name, *arg)
            return await handle.result(), await handle.query(ImplementWorkflow.status)


async def test_happy_path_approved_and_merged_in_round_one():
    stage, status = await run_job()
    assert stage == Stage.MERGED and status["round"] == 1 and status["waits"] == 0
    assert status["pr_url"].endswith("/pull/7")
    assert CALLS.count("run_reviewer") == 2  # one per routed lens
    order = [CALLS.index(c) for c in ("run_gate", "ensure_pr", "run_reviewer", "run_approver", "sync_and_merge",
                                      "cleanup_worktree")]
    assert order == sorted(order)


async def test_needs_info_waits_and_rejection_ends_the_job():
    stage, _ = await run_job(decision=("NEEDS-INFO",), signals=[REJECT])
    assert stage == Stage.REJECTED and "run_spec_writer" not in CALLS and "reject_job" in CALLS


async def test_reject_at_intake():
    stage, _ = await run_job(decision=("REJECT",))
    assert stage == Stage.REJECTED
    assert LABEL_CHANGES == [LabelChange(1, remove_flow_label=FlowName.IMPLEMENT)]  # edit_labels resolves the label


async def test_gate_fail_loops_back_to_build_without_reviewing():
    stage, status = await run_job(gates=("FAIL", "PASS"))
    assert stage == Stage.MERGED and status["round"] == 2
    assert CALLS.count("run_builder") == 2 and CALLS.count("run_reviewer") == 2


async def test_review_changes_loops_back_to_build():
    stage, status = await run_job(gates=("PASS", "PASS"), reviews=(("PASS", "CHANGES"), ("PASS",)))
    assert stage == Stage.MERGED and status["round"] == 2
    assert CALLS.count("run_builder") == 2 and CALLS.count("ensure_pr") == 1


async def test_approver_escalation_then_pr_merged_by_hand():
    stage, status = await run_job(approvals=("ESCALATE",), signals=[("pr_merged",)])
    assert stage == Stage.MERGED and "sync_and_merge" not in CALLS and status["waits"] == 1


async def test_approver_escalation_then_reject():
    stage, _ = await run_job(approvals=("ESCALATE",), signals=[REJECT])
    assert stage == Stage.REJECTED and "reject_job" in CALLS and "cleanup_worktree" in CALLS


async def test_merge_failure_escalates_and_feedback_runs_another_round():
    stage, status = await run_job(gates=("PASS", "PASS"), approvals=("APPROVE", "APPROVE"),
                                  merges=(False, True), signals=[("human_feedback", "rebase please")])
    assert stage == Stage.MERGED and status["round"] == 2 and status["waits"] == 1
    assert "write_feedback" in CALLS and CALLS.count("sync_and_merge") == 2


async def test_round_budget_exhausted_escalates_and_feedback_resets_budget():
    stage, status = await run_job(gates=("PASS",) * 4, reviews=(("CHANGES",),) * 3 + (("PASS",),),
                                  signals=[("human_feedback", "try the other approach")])
    assert stage == Stage.MERGED and status["round"] == 4 and status["waits"] == 1
    assert CALLS.count("run_builder") == 4


async def test_gate_fails_every_round_escalates_without_reviewing():
    stage, _ = await run_job(gates=("FAIL",) * 3, signals=[REJECT])
    assert stage == Stage.REJECTED and "run_reviewer" not in CALLS and "ensure_pr" not in CALLS


async def test_blocked_builder_escalates():
    stage, _ = await run_job(build="BLOCKED", signals=[REJECT])
    assert stage == Stage.REJECTED and "run_gate" not in CALLS


async def test_needs_info_resumes_intake_after_author_replies():
    stage, status = await run_job(decision=("NEEDS-INFO", "ACCEPT"), signals=[("author_replied",)])
    assert stage == Stage.MERGED and status["waits"] == 1
    assert CALLS.count("run_intake") == 2 and "restart_intake" in CALLS
