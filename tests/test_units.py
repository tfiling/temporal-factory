import pytest

from factory.core.config import load_config
from factory.core.parsing import body_after_header, header, section
from factory.core.routing import route


def test_route_merges_risk_and_surfaces():
    cfg = load_config()
    assert route(cfg, "low", []) == {"code": "haiku"}
    assert route(cfg, "high", ["ui", "security"]) == {
        "code": "sonnet", "ux": "sonnet", "ui": "haiku", "security": "opus"}


def test_route_rejects_unknown():
    with pytest.raises(ValueError):
        route(load_config(), "extreme", [])
    with pytest.raises(ValueError):
        route(load_config(), "low", ["billing"])


def test_parsing(tmp_path):
    f = tmp_path / "intake.md"
    f.write_text("DECISION: ACCEPT\nRISK: low\n\n## Scope\nDo X.\n\n## Why\nBecause.\n")
    assert header(f) == {"DECISION": "ACCEPT", "RISK": "low"}
    assert section(f, "Scope") == "Do X."
    assert section(f, "Nope") is None
    assert body_after_header(f).startswith("## Scope")


def test_stage_wire_compat():
    """JobState round-trips through the Temporal data converter with plain-string stages."""
    import asyncio
    from temporalio.converter import DataConverter
    from factory.core.models import JobState, Stage

    async def go():
        conv = DataConverter.default
        payloads = await conv.encode([JobState(7, Stage.NEEDS_HUMAN, 1.5)])
        assert b'"needs-human"' in payloads[0].data
        (state,) = await conv.decode(payloads, [JobState])
        assert state.stage is Stage.NEEDS_HUMAN
        old = await conv.encode([{"issue": 7, "stage": "merged", "cost_usd": 0.0}])
        assert (await conv.decode(old, [JobState]))[0].stage is Stage.MERGED

    asyncio.run(go())


def test_flow_for_labels_first_configured_match_wins():
    from factory.core.config import Flow, flow_for_labels
    from factory.core.models import FlowName
    cfg = load_config().model_copy(update={"flows": {FlowName.CI_DRY_RUN: Flow(label="factory:other"),
                                                     FlowName.IMPLEMENT: Flow(label="factory")}})
    assert flow_for_labels(cfg, ["factory", "factory:other"]) is FlowName.CI_DRY_RUN
    assert flow_for_labels(cfg, ["bug", "factory"]) is FlowName.IMPLEMENT
    assert flow_for_labels(cfg, ["bug"]) is None


def test_configured_flows_are_registered():
    from factory.core.models import FlowName
    from factory.flows.registry import FLOWS, workflow_id
    assert set(load_config().flows) <= set(FLOWS) == set(FlowName)
    assert workflow_id(FlowName.IMPLEMENT, 7) == "factory-job-7"  # in-flight runs and the CLI rely on it


def test_queue_keys_legacy_job_states_by_workflow_id():
    from factory.core.models import JobState, Stage
    from factory.flows.queue import _key
    assert _key(JobState(7, Stage.BUILD)) == "factory-job-7"
    assert _key(JobState(7, Stage.BUILD, workflow_id="factory-x-7")) == "factory-x-7"


def test_config_rejects_label_on_non_issue_driven_flow():
    from factory.core.config import Flow
    from factory.core.models import FlowName
    from factory.flows.registry import config_errors
    assert config_errors({FlowName.IMPLEMENT: Flow(label="factory"), FlowName.CI_DRY_RUN: Flow()}) == []
    assert config_errors({FlowName.CI_DRY_RUN: Flow(label="x")}) == [
        "config.json flow 'ci-dry-run' has a label but is not issue-driven"]
    assert config_errors(load_config().flows) == []


@pytest.mark.parametrize("cmd", ["run", "status", "merged"])
def test_cli_rejects_non_issue_driven_flow(cmd):
    import asyncio
    from factory.cli import main
    with pytest.raises(SystemExit, match="not issue-driven"):
        asyncio.run(main([cmd, "5", "--flow", "ci-dry-run"]))


def test_edit_labels_removes_the_flow_label(monkeypatch):
    from factory.activities import github
    from factory.core.config import Flow
    from factory.core.models import FlowName, LabelChange
    cfg = load_config().model_copy(update={"flows": {FlowName.IMPLEMENT: Flow(label="factory:impl")}})
    calls = []
    monkeypatch.setattr("factory.activities.github.load_config", lambda: cfg)
    monkeypatch.setattr(github, "gh", lambda *a: calls.append(a))
    github.edit_labels(LabelChange(5, remove_flow_label=FlowName.IMPLEMENT))
    assert calls == [("issue", "edit", "5", "--remove-label", "factory:impl")]


def test_flows_are_required():
    import pytest
    from pydantic import ValidationError
    data = load_config().model_dump(exclude={"flows"})
    with pytest.raises(ValidationError):
        type(load_config()).model_validate(data)


def test_config_rejects_unknown_flow_name():
    from pydantic import ValidationError
    data = load_config().model_dump()
    data["flows"]["nope"] = {}
    with pytest.raises(ValidationError, match="nope"):
        type(load_config()).model_validate(data)


def test_cli_rejects_unknown_flow_and_lists_valid_names():
    import asyncio
    from factory.cli import main
    with pytest.raises(SystemExit, match="unknown flow 'nope'; flows: implement, ci-dry-run"):
        asyncio.run(main(["run", "5", "--flow", "nope"]))


@pytest.mark.parametrize("flows", [{}, {"ci-dry-run": {}}])  # flow has no entry / no label
def test_edit_labels_skips_a_flow_without_a_label(monkeypatch, flows):
    from factory.activities import github
    from factory.core.models import FlowName, LabelChange, LabelKind
    cfg = type(load_config()).model_validate(load_config().model_dump() | {"flows": flows})
    calls = []
    monkeypatch.setattr("factory.activities.github.load_config", lambda: cfg)
    monkeypatch.setattr(github, "gh", lambda *a: calls.append(a))
    github.edit_labels(LabelChange(5, remove=[LabelKind.NEEDS_HUMAN], remove_flow_label=FlowName.CI_DRY_RUN))
    assert calls == [("issue", "edit", "5", "--remove-label", cfg.labels.needs_human)]


def test_label_kinds_match_config_labels():
    from factory.core.config import Labels
    from factory.core.models import LabelKind
    assert {k.value for k in LabelKind} == set(Labels.model_fields)


def test_label_payloads_wire_compat():
    """Payloads recorded with plain strings decode into enums."""
    import asyncio
    from temporalio.converter import DataConverter
    from factory.core.models import FlowName, LabelChange, LabelKind, QueueIssue

    async def go():
        conv = DataConverter.default
        old = await conv.encode([{"number": 5, "add": ["needs_info"], "remove": ["needs_human"],
                                  "remove_flow_label": "ci-dry-run"},
                                 {"number": 5, "needs_info": False, "replied": False, "flow": "implement"}])
        change, issue = await conv.decode(old, [LabelChange, QueueIssue])
        assert change.add[0] is LabelKind.NEEDS_INFO and change.remove[0] is LabelKind.NEEDS_HUMAN
        assert change.remove_flow_label is FlowName.CI_DRY_RUN and issue.flow is FlowName.IMPLEMENT

    asyncio.run(go())
