"""FactoryWorkflow: state, signals, query and queue reporting shared by every flow.

Subclasses add `@workflow.defn` and a `@workflow.run` that wraps its body in `self.reporting(...)`.
Steps (`flows/steps/`) read and update this state.
"""

from collections.abc import Awaitable, Callable

from temporalio import workflow
from temporalio.exceptions import TemporalError

with workflow.unsafe.imports_passed_through():
    from factory.activities.merge import cleanup_worktree
    from factory.core.models import FlowName, JobState, Stage

from factory.flows.options import GIT


class FactoryWorkflow:
    flow: FlowName  # subclasses set it
    run: Callable[..., Awaitable[Stage]]  # subclasses define it with @workflow.run; declared for type checkers

    def __init__(self) -> None:
        self.stage: Stage = Stage.STARTING
        self.round = 0
        self.issue = 0
        self.waits = 0
        self.pr_url: str | None = None
        self.pr_number: int | None = None
        self.cost_usd = 0.0
        self.job_dir: str | None = None  # job folder with every artifact, once set up
        self.session: str | None = None  # builder session, resumed across rounds
        # Set by signals; only consumed while the flow waits for a human or the author.
        self.feedback: list[str] = []
        self.rejection: str | None = None
        self.merged = False
        self.replied = False

    @workflow.query
    def status(self) -> dict:
        return {"stage": self.stage, "round": self.round, "waits": self.waits,
                "pr_url": self.pr_url, "cost_usd": self.cost_usd, "job_dir": self.job_dir}

    @workflow.signal
    def author_replied(self) -> None:
        self.replied = True

    @workflow.signal
    def human_feedback(self, text: str) -> None:
        self.feedback.append(text)

    @workflow.signal
    def reject(self, reason: str) -> None:
        self.rejection = reason

    @workflow.signal
    def pr_merged(self) -> None:
        self.merged = True

    async def notify(self, stage: Stage | None = None) -> None:
        """Tell the parent queue (if any) whether this flow is working, waiting or done."""
        parent = workflow.info().parent
        if parent is None:
            return
        try:
            await workflow.get_external_workflow_handle(parent.workflow_id).signal(
                "job_state", JobState(self.issue, stage or self.stage, self.cost_usd,
                                      workflow.info().workflow_id))
        except TemporalError:
            pass  # the queue isn't running; the flow doesn't depend on it

    async def reporting(self, body: Awaitable[Stage]) -> Stage:
        """Run the flow body and report its terminal stage (or FAILED) to the queue."""
        try:
            stage = await body
        except Exception:
            await self.notify(Stage.FAILED)
            raise
        await self.notify(stage)
        return stage

    async def finish(self, job, stage: Stage) -> Stage:
        await workflow.execute_activity(cleanup_worktree, job, **GIT)
        self.stage = stage
        return stage
