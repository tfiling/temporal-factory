import pytest

from factory.config import load_config
from factory.parsing import body_after_header, header, section
from factory.routing import route


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
    from factory.models import JobState, Stage

    async def go():
        conv = DataConverter.default
        payloads = await conv.encode([JobState(7, Stage.NEEDS_HUMAN, 1.5)])
        assert b'"needs-human"' in payloads[0].data
        (state,) = await conv.decode(payloads, [JobState])
        assert state.stage is Stage.NEEDS_HUMAN
        old = await conv.encode([{"issue": 7, "stage": "merged", "cost_usd": 0.0}])
        assert (await conv.decode(old, [JobState]))[0].stage is Stage.MERGED

    asyncio.run(go())
