"""Every flow by name: its workflow class and workflow id. The worker, queue and CLI read this."""

from dataclasses import dataclass
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from factory.core.models import FlowName

from factory.flows.base import FactoryWorkflow
from factory.flows.ci_dry_run import CiDryRunWorkflow
from factory.flows.implement import ImplementWorkflow


@dataclass(frozen=True)
class FlowSpec:
    workflow: type[FactoryWorkflow]
    id_prefix: str  # workflow id = <id_prefix>-<key>, key = issue/PR number or a timestamp
    issue_driven: bool  # run() takes an int issue number: the queue (via `label`) and CLI issue commands can start it


FLOWS: dict[FlowName, FlowSpec] = {
    FlowName.IMPLEMENT: FlowSpec(ImplementWorkflow, "factory-job", issue_driven=True),  # historical id, kept for in-flight runs
    FlowName.CI_DRY_RUN: FlowSpec(CiDryRunWorkflow, "factory-ci-dry-run", issue_driven=False),
}
assert set(FLOWS) == set(FlowName), "every FlowName needs a FLOWS entry"


def workflow_id(flow: FlowName, key: int | str) -> str:
    return f"{FLOWS[flow].id_prefix}-{key}"


def config_errors(flows: dict) -> list[str]:
    """Problems with config.json `flows` (FlowName -> Flow) that pydantic can't catch; empty when valid."""
    return [f"config.json flow {n.value!r} has a label but is not issue-driven" for n, f in flows.items()
            if f.label and not FLOWS[n].issue_driven]
