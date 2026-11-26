"""CiDryRunWorkflow with mocked activities: gate verdict → stage, cleanup on every outcome."""

import uuid

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from factory.core.models import (GIT_QUEUE, ORCHESTRATION_QUEUE, DryRunInput, GateRequest, GateResult, Job,
                                 Stage)
from factory.flows.base import FactoryWorkflow
from factory.flows.ci_dry_run import CiDryRunWorkflow

CALLS: list[str] = []


def make_activities(verdict="PASS", gate_error=False, cleanup_error=False):
    CALLS.clear()

    @activity.defn(name="setup_dry_run")
    async def setup_dry_run(inp: DryRunInput) -> Job:
        CALLS.append(f"setup_dry_run:{inp.key}")
        return Job(f"dry-run-{inp.key}", 0, "dry", f"/d/{inp.key}", "/r", "/w", "factory/dry", inp.base or "main")

    @activity.defn(name="create_worktree")
    async def create_worktree(_job: Job) -> None:
        CALLS.append("create_worktree")

    @activity.defn(name="run_gate")
    async def run_gate(_req: GateRequest) -> GateResult:
        CALLS.append("run_gate")
        if gate_error:
            raise ApplicationError("disk full", non_retryable=True)
        return GateResult(verdict, "abc", 0 if verdict == "PASS" else 1, [])

    @activity.defn(name="cleanup_worktree")
    async def cleanup_worktree(_job: Job) -> None:
        CALLS.append("cleanup_worktree")
        if cleanup_error:
            raise ApplicationError("git queue down", non_retryable=True)

    return [setup_dry_run, create_worktree, run_gate, cleanup_worktree]


async def run_dry(inp=DryRunInput(), **kw):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        acts = make_activities(**kw)
        async with (Worker(env.client, task_queue=ORCHESTRATION_QUEUE, workflows=[CiDryRunWorkflow]),
                    Worker(env.client, task_queue=GIT_QUEUE, activities=acts)):
            handle = await env.client.start_workflow(
                CiDryRunWorkflow.run, inp, id=f"t-{uuid.uuid4()}", task_queue=ORCHESTRATION_QUEUE)
            return await handle.result(), await handle.query(FactoryWorkflow.status)


async def test_passing_checks_then_cleanup():
    stage, status = await run_dry(DryRunInput("main", "k1"))
    assert stage == Stage.PASSED and status["job_dir"] == "/d/k1"
    assert CALLS == ["setup_dry_run:k1", "create_worktree", "run_gate", "cleanup_worktree"]


async def test_failing_checks_still_cleans_up():
    stage, _ = await run_dry(verdict="FAIL")
    assert stage == Stage.CHECKS_FAILED and CALLS[-1] == "cleanup_worktree"


async def test_key_defaults_to_the_start_time():
    await run_dry()
    assert CALLS[0].startswith("setup_dry_run:") and len(CALLS[0].split(":")[1]) == len("20261126-120000")


async def test_activity_error_cleans_up_and_fails():
    with pytest.raises(WorkflowFailureError):
        await run_dry(gate_error=True)
    assert CALLS[-1] == "cleanup_worktree"


async def test_cleanup_error_does_not_mask_gate_error():
    with pytest.raises(WorkflowFailureError) as exc:
        await run_dry(gate_error=True, cleanup_error=True)
    assert CALLS[-1] == "cleanup_worktree"
    activity_err = exc.value.cause
    assert isinstance(activity_err, ActivityError)
    app_err = activity_err.cause
    assert isinstance(app_err, ApplicationError)
    assert app_err.message == "disk full"
