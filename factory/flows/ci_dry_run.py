"""CiDryRunWorkflow: run the checks on an up-to-date base branch in a throwaway worktree.

setup → worktree off origin/<base> → gate → cleanup (always). No issue, agents or PR.
Keep features/temporal_factory/Flows/CI dry run.md in sync with any change here.
"""

from dataclasses import replace

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from factory.activities.gate import run_gate
    from factory.activities.git import create_worktree
    from factory.activities.github import setup_dry_run
    from factory.activities.merge import cleanup_worktree
    from factory.core.models import DryRunInput, FlowName, GateRequest, Stage

from factory.flows.base import FactoryWorkflow
from factory.flows.options import GATE, GIT


@workflow.defn(name="CiDryRunWorkflow")
class CiDryRunWorkflow(FactoryWorkflow):
    flow = FlowName.CI_DRY_RUN

    @workflow.run
    async def run(self, inp: DryRunInput) -> Stage:
        return await self.reporting(self._run(inp))

    async def _run(self, inp: DryRunInput) -> Stage:
        inp = replace(inp, key=inp.key or workflow.now().strftime("%Y%m%d-%H%M%S"))
        job = await workflow.execute_activity(setup_dry_run, inp, **GIT)
        self.job_dir, self.round = job.dir, 1
        try:
            await workflow.execute_activity(create_worktree, job, **GIT)
            self.stage = Stage.CHECKS
            gate = await workflow.execute_activity(run_gate, GateRequest(job, 1), **GATE)
        except Exception:
            try:
                await workflow.execute_activity(cleanup_worktree, job, **GIT)
            except Exception as cleanup_err:  # keep the original error as the failure cause
                workflow.logger.warning("cleanup_worktree failed after error: %s", cleanup_err)
            raise
        return await self.finish(job, Stage.PASSED if gate.verdict == "PASS" else Stage.CHECKS_FAILED)
