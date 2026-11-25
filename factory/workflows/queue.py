"""FactoryQueueWorkflow: starts a JobWorkflow per labeled issue within the concurrency cap (v2 `cmd_queue`).

Jobs report their state back with the `job_state` signal, so the queue keeps no child handles and
survives continue-as-new. Waiting jobs (needs-info, needs-human) don't hold a slot.
"""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import TemporalError, WorkflowAlreadyStartedError
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from factory.activities.github import list_queue_issues
    from factory.models import GIT_QUEUE, ORCHESTRATION_QUEUE, JobState, QueueInput, Stage
    from factory.workflows.job import JobWorkflow

TERMINAL = {Stage.MERGED, Stage.REJECTED, Stage.FAILED}
WAITING = {Stage.NEEDS_INFO, Stage.NEEDS_HUMAN}
QUEUE_ID = "factory-queue"


def job_id(issue: int) -> str:
    return f"factory-job-{issue}"


@workflow.defn(name="FactoryQueueWorkflow")
class FactoryQueueWorkflow:
    def __init__(self) -> None:
        self.jobs: dict[str, JobState] = {}
        self._poke = False

    @workflow.signal
    def job_state(self, state: JobState) -> None:
        if state.stage in TERMINAL:
            self.jobs.pop(str(state.issue), None)
        else:
            self.jobs[str(state.issue)] = state

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
        self.jobs = dict(inp.jobs)
        while True:
            snap = await workflow.execute_activity(
                list_queue_issues, task_queue=GIT_QUEUE, start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=5, backoff_coefficient=2.0))
            for issue in snap.issues:
                key = str(issue.number)
                if issue.needs_info and issue.replied and self._working() < snap.concurrency:
                    try:
                        await workflow.get_external_workflow_handle(job_id(issue.number)).signal("author_replied")
                        self.jobs[key] = JobState(issue.number, Stage.RESUMING, self.jobs[key].cost_usd
                                                  if key in self.jobs else 0.0)
                    except TemporalError:
                        pass  # no running job for this issue
                elif key not in self.jobs and self._working() < snap.concurrency:
                    try:
                        await workflow.start_child_workflow(
                            JobWorkflow.run, issue.number, id=job_id(issue.number),
                            task_queue=ORCHESTRATION_QUEUE, parent_close_policy=ParentClosePolicy.ABANDON,
                            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY)
                    except WorkflowAlreadyStartedError:
                        continue  # already running (e.g. started by the CLI) or finished
                    self.jobs[key] = JobState(issue.number, Stage.STARTING)

            if workflow.info().is_continue_as_new_suggested():
                workflow.continue_as_new(QueueInput(inp.poll_seconds, self.jobs))
            try:
                await workflow.wait_condition(lambda: self._poke, timeout=timedelta(seconds=inp.poll_seconds))
            except asyncio.TimeoutError:
                pass
            self._poke = False
