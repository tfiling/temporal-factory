"""FactoryQueueWorkflow: concurrency cap, one job per issue, jobs report back via signals."""

import asyncio

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from factory.core.models import (AGENTS_QUEUE, GIT_QUEUE, ORCHESTRATION_QUEUE, AgentRequest, AgentResult,
                            BuildResult, DecisionResult, GateResult, IntakeResult, Job, MergeResult,
                            FlowName, JobState, PrInfo, QueueInput, QueueIssue, QueueSnapshot, ReviewResult,
                            Stage)
from factory.flows.implement import ImplementWorkflow
from factory.flows.queue import FactoryQueueWorkflow

STATE = {"running": 0, "max": 0, "intakes": 0, "merged": 0, "polls": 0}


def activities(concurrency: int, issues: list[int], fail_polls: int = 0, extra=()):
    def rec(name, value):
        @activity.defn(name=name)
        async def fn(_arg=None):
            return value
        return fn

    @activity.defn(name="list_queue_issues")
    async def list_queue_issues() -> QueueSnapshot:
        STATE["polls"] += 1
        if STATE["polls"] <= fail_polls:
            raise ApplicationError("config.json: unknown flow", non_retryable=True)
        return QueueSnapshot([*extra, *(QueueIssue(n, False, False) for n in issues)], concurrency)

    @activity.defn(name="setup_job")
    async def setup_job(issue: int) -> Job:
        return Job(f"{issue:03d}-x", issue, "x", "/d", "/r", "/w", f"factory/{issue}", "main")

    @activity.defn(name="run_intake")
    async def run_intake(_req: AgentRequest) -> IntakeResult:
        STATE["intakes"] += 1
        return IntakeResult("ACCEPT", "low", [], False, "body", AgentResult())

    @activity.defn(name="run_builder")
    async def run_builder(_req: AgentRequest) -> BuildResult:
        STATE["running"] += 1
        STATE["max"] = max(STATE["max"], STATE["running"])
        await asyncio.sleep(0.3)  # real time: keeps the job "working" while the queue polls
        STATE["running"] -= 1
        return BuildResult("READY", "", AgentResult("s", 1.0))

    @activity.defn(name="cleanup_worktree")
    async def cleanup_worktree(_job: Job) -> None:
        STATE["merged"] += 1

    return [
        list_queue_issues, setup_job, run_intake, run_builder, cleanup_worktree,
        rec("route_job", {"code": "haiku"}), rec("comment_issue", None), rec("edit_labels", None),
        rec("create_worktree", None), rec("run_spec_writer", AgentResult()), rec("verify_build", ""),
        rec("run_gate", GateResult("PASS", "abc", 0, [])), rec("ensure_pr", PrInfo(7, "https://x/pull/7")),
        rec("run_reviewer", ReviewResult("code", "PASS")),
        rec("run_approver", DecisionResult("APPROVE", "")), rec("sync_and_merge", MergeResult(True)),
    ]


async def run_queue(acts, jobs=None):
    async with await WorkflowEnvironment.start_local() as env:
        async with (Worker(env.client, task_queue=ORCHESTRATION_QUEUE,
                           workflows=[ImplementWorkflow, FactoryQueueWorkflow], activities=acts),
                    Worker(env.client, task_queue=AGENTS_QUEUE, activities=acts),
                    Worker(env.client, task_queue=GIT_QUEUE, activities=acts)):
            queue = await env.client.start_workflow(
                FactoryQueueWorkflow.run, QueueInput(poll_seconds=0.1, jobs=jobs or {}), id="q",
                task_queue=ORCHESTRATION_QUEUE)
            for _ in range(200):
                if STATE["merged"] == 3:
                    break
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.5)  # let the queue poll again: finished jobs must not restart
            status = await queue.query(FactoryQueueWorkflow.status)
            await queue.terminate()
    return status


async def test_queue_runs_each_issue_once_within_the_concurrency_cap():
    STATE.update(running=0, max=0, intakes=0, merged=0, polls=0)
    status = await run_queue(activities(concurrency=1, issues=[1, 2, 3]))
    assert STATE["merged"] == 3 and STATE["intakes"] == 3  # each issue ran once, never re-run
    assert STATE["max"] == 1  # concurrency 1
    assert status["jobs"] == {} and status["working"] == 0  # terminal jobs are dropped


async def test_queue_survives_failed_polls_and_skips_flows_it_cannot_start():
    STATE.update(running=0, max=0, intakes=0, merged=0, polls=0)
    status = await run_queue(activities(concurrency=3, issues=[1, 2], fail_polls=2,
                                        extra=[QueueIssue(9, False, False, FlowName.CI_DRY_RUN)]))
    assert STATE["polls"] > 3 and STATE["merged"] == 2 and STATE["intakes"] == 2  # #9 never started
    assert status["jobs"] == {}


@pytest.mark.parametrize("stage", [Stage.BUILD, Stage.NEEDS_HUMAN])
async def test_queue_starts_no_second_job_for_an_issue_that_matches_another_flow(stage):
    STATE.update(running=0, max=0, intakes=0, merged=0, polls=0)
    job = JobState(1, stage, workflow_id="factory-other-1")  # opened under the flow the issue had before
    status = await run_queue(activities(concurrency=3, issues=[1, 2, 3, 4]), jobs={job.workflow_id: job})
    assert STATE["merged"] == 3 and STATE["intakes"] == 3  # #2-4 ran, #1 got no second workflow
    assert list(status["jobs"]) == ["factory-other-1"]
