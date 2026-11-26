"""ImplementWorkflow: one GitHub issue → merged PR.

intake → route → spec → [build → gate → review]* → approve → merge, with escalation to a human
(signals: human_feedback, reject, pr_merged). Ported from the v2 state machine in factory/bin/job.
Keep features/temporal_factory/Flows/Implement.md in sync with any change here.
"""

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from factory.activities.github import setup_job
    from factory.core.models import FlowName, Stage

from factory.flows.base import FactoryWorkflow
from factory.flows.options import GIT
from factory.flows.steps.build import build_rounds
from factory.flows.steps.intake import intake, reject_at_intake
from factory.flows.steps.prepare import prepare


@workflow.defn(name="JobWorkflow")  # historical type name: in-flight runs and the queue use it
class ImplementWorkflow(FactoryWorkflow):
    flow = FlowName.IMPLEMENT

    @workflow.run
    async def run(self, issue: int) -> Stage:
        self.issue = issue
        return await self.reporting(self._run(issue))

    async def _run(self, issue: int) -> Stage:
        job = await workflow.execute_activity(setup_job, issue, **GIT)
        self.job_dir = job.dir
        result = await intake(self, job)
        if result is None:  # rejected while waiting for the author
            return await self.finish(job, Stage.REJECTED)
        if result.decision == "REJECT":
            return await reject_at_intake(self, job, result)
        reviewers = await prepare(self, job, result)
        return await build_rounds(self, job, reviewers)
