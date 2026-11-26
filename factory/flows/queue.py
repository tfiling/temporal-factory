"""FactoryQueueWorkflow: starts a flow per labeled issue within the concurrency cap (v2 `cmd_queue`).

The flow comes from the issue's labels (config `flows`, resolved by `list_queue_issues`). Flows report
their state back with the `job_state` signal, so the queue keeps no child handles and survives
continue-as-new. Waiting flows (needs-info, needs-human) don't hold a slot.
"""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ActivityError, TemporalError, WorkflowAlreadyStartedError
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from factory.activities.github import list_queue_issues
    from factory.core.models import (GIT_QUEUE, ORCHESTRATION_QUEUE, FlowName, JobState, QueueInput, QueueSnapshot,
                                     Stage)

from factory.flows.registry import FLOWS, workflow_id

TERMINAL = {Stage.MERGED, Stage.REJECTED, Stage.FAILED, Stage.PASSED, Stage.CHECKS_FAILED}
WAITING = {Stage.NEEDS_INFO, Stage.NEEDS_HUMAN}
QUEUE_ID = "factory-queue"


def _key(state: JobState) -> str:
    return state.workflow_id or workflow_id(FlowName.IMPLEMENT, state.issue)


@workflow.defn(name="FactoryQueueWorkflow")
class FactoryQueueWorkflow:
    def __init__(self) -> None:
        self.jobs: dict[str, JobState] = {}
        self._poke = False

    @workflow.signal
    def job_state(self, state: JobState) -> None:
        key = _key(state)
        if state.stage in TERMINAL:
            self.jobs.pop(key, None)
        else:
            self.jobs[key] = state

    @workflow.signal
    def poke(self) -> None:
        self._poke = True

    @workflow.query
    def status(self) -> dict:
        return {"working": self._working(),
                "jobs": {k: {"stage": j.stage.value, "cost_usd": j.cost_usd} for k, j in self.jobs.items()}}

    def _working(self) -> int:
        return sum(1 for j in self.jobs.values() if j.stage not in WAITING)

    @workflow.run
    async def run(self, inp: QueueInput) -> None:
        self.jobs = {_key(s): s for s in inp.jobs.values()}  # older runs keyed jobs by issue
        while True:
            snap: QueueSnapshot | None
            try:
                snap = await workflow.execute_activity(
                    list_queue_issues, task_queue=GIT_QUEUE, start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=5, backoff_coefficient=2.0))
            except ActivityError as err:  # e.g. config.json edited into an invalid state: keep polling
                workflow.logger.warning("list_queue_issues failed, retrying next poll: %s", err.cause or err)
                snap = None
            issues, concurrency = (snap.issues, snap.concurrency) if snap else ([], 0)
            for issue in issues:
                spec = FLOWS.get(issue.flow)
                if spec is None or not spec.issue_driven:  # config labels a flow the queue can't start
                    workflow.logger.warning("issue #%s: flow %s can't be started by the queue; skipped",
                                            issue.number, issue.flow)
                    continue
                key = workflow_id(issue.flow, issue.number)
                current = next((k for k, j in self.jobs.items() if j.issue == issue.number), key)
                if current != key:  # relabeled mid-job: the first job keeps the issue until it ends
                    workflow.logger.warning("issue #%s: now matches flow %s but %s is still open; not starting",
                                            issue.number, issue.flow, current)
                    key = current
                if issue.needs_info and issue.replied and self._working() < concurrency:
                    try:
                        await workflow.get_external_workflow_handle(key).signal("author_replied")
                        self.jobs[key] = JobState(issue.number, Stage.RESUMING, self.jobs[key].cost_usd
                                                  if key in self.jobs else 0.0, key)
                    except TemporalError:
                        pass  # no running job for this issue
                elif key not in self.jobs and self._working() < concurrency:
                    try:
                        await workflow.start_child_workflow(
                            spec.workflow.run, issue.number, id=key,
                            task_queue=ORCHESTRATION_QUEUE, parent_close_policy=ParentClosePolicy.ABANDON,
                            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY)
                    except WorkflowAlreadyStartedError:
                        continue  # already running (e.g. started by the CLI) or finished
                    self.jobs[key] = JobState(issue.number, Stage.STARTING, workflow_id=key)

            if workflow.info().is_continue_as_new_suggested():
                workflow.continue_as_new(QueueInput(inp.poll_seconds, self.jobs))
            try:
                await workflow.wait_condition(lambda: self._poke, timeout=timedelta(seconds=inp.poll_seconds))
            except asyncio.TimeoutError:
                pass
            self._poke = False
