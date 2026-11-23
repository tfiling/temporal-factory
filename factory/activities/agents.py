"""Agent activities: each v2 agent runs through the Claude Agent SDK with its v2 prompt."""

import re
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from temporalio import activity
from temporalio.exceptions import ApplicationError

from factory.config import load_config
from factory.models import (AgentRequest, AgentResult, BuildResult, DecisionResult, IntakeResult,
                            ReviewResult)
from factory.parsing import body_after_header, first_line, header, section

PROMPTS = Path(__file__).parents[1] / "prompts"
TOOLS = {
    "intake": ["Read", "Grep", "Glob", "Write"],
    "spec-writer": ["Read", "Grep", "Glob", "Bash", "Write"],
    "builder": ["Read", "Grep", "Glob", "Bash", "Edit", "Write"],
}
REVIEWER_TOOLS = ["Read", "Grep", "Glob", "Bash", "Write"]  # also the approver's
PORT_OFFSET = {"builder": 0, "reviewer-ux": 1, "reviewer-ui": 2}  # dev-server port = base + step*issue + offset


def job_header(req: AgentRequest) -> str:
    j, cfg = req.job, load_config()
    port = f" Port: {cfg.ports.base + cfg.ports.step * j.issue + PORT_OFFSET[req.role]}." \
        if req.role in PORT_OFFSET else ""
    return (f"Job: {j.id}. Job folder: {j.dir}/. Main checkout: {j.repo}. Worktree: {j.worktree}. "
            f"Branch: {j.branch}. Base: origin/{j.base}. Issue: #{j.issue}. "
            f"Checks command: {cfg.checks_cmd}. Round: {req.round}.{port}")


async def _run_agent(req: AgentRequest) -> AgentResult:
    cfg = load_config()
    options = ClaudeAgentOptions(
        system_prompt=(PROMPTS / f"{req.role}.md").read_text(),
        allowed_tools=TOOLS.get(req.role, REVIEWER_TOOLS),
        model=cfg.models[req.model or cfg.roles[req.role]],
        cwd=req.job.repo if req.role == "intake" else req.job.worktree,
        add_dirs=[req.job.dir],
        permission_mode="bypassPermissions",
        resume=req.session_id,
    )
    result = None
    async for msg in query(prompt=f"{job_header(req)}\n\n{req.message}", options=options):
        activity.heartbeat()
        if isinstance(msg, ResultMessage):
            result = msg
    if result is None or result.is_error:
        raise RuntimeError(f"{req.role} agent failed: {getattr(result, 'result', 'no result')}")
    return AgentResult(session_id=result.session_id, cost_usd=result.total_cost_usd or 0.0,
                       reply=result.result or "")


@activity.defn
async def run_intake(req: AgentRequest) -> IntakeResult:
    agent = await _run_agent(req)
    path = Path(req.job.dir) / "intake.md"
    if not path.exists():
        raise ApplicationError("intake wrote no intake.md", non_retryable=True)
    h = header(path)
    decision = h.get("DECISION", "")
    if decision not in {"ACCEPT", "NEEDS-INFO", "REJECT"}:
        raise ApplicationError(f"intake.md has DECISION {decision!r}", non_retryable=True)
    surfaces = [s.strip() for s in h.get("SURFACES", "none").split(",") if s.strip() not in ("", "none")]
    return IntakeResult(decision=decision, risk=h.get("RISK", "").lower(), surfaces=surfaces,
                        rescoped=h.get("RESCOPED", "no").lower() == "yes",
                        body=body_after_header(path), agent=agent)


@activity.defn
async def run_spec_writer(req: AgentRequest) -> AgentResult:
    agent = await _run_agent(req)
    if not (Path(req.job.dir) / "spec.md").exists():
        raise ApplicationError("spec-writer wrote no spec.md", non_retryable=True)
    return agent


@activity.defn
async def run_reviewer(req: AgentRequest) -> ReviewResult:
    agent = await _run_agent(req)
    lens = req.role.removeprefix("reviewer-")
    line = first_line(Path(req.job.dir) / f"round-{req.round}" / f"review-{lens}.md")
    m = re.fullmatch(r"VERDICT:\s*(PASS|CHANGES)", line or "")
    if not m:
        raise ApplicationError(f"review-{lens}.md first line is {line!r}, not a verdict", non_retryable=True)
    return ReviewResult(lens=lens, verdict=m.group(1), cost_usd=agent.cost_usd)


@activity.defn
async def run_approver(req: AgentRequest) -> DecisionResult:
    agent = await _run_agent(req)
    path = Path(req.job.dir) / "decision.md"
    decision = first_line(path)
    if decision not in {"APPROVE", "ESCALATE"}:
        raise ApplicationError(f"decision.md first line is {decision!r}", non_retryable=True)
    return DecisionResult(decision=decision, body=path.read_text().split("\n", 1)[1].strip(), agent=agent)


@activity.defn
async def run_builder(req: AgentRequest) -> BuildResult:
    agent = await _run_agent(req)
    path = Path(req.job.dir) / "build.md"
    status = (first_line(path) or "").removeprefix("STATUS:").strip()
    if status not in {"READY", "BLOCKED"}:
        raise ApplicationError(f"build.md has STATUS {status!r}", non_retryable=True)
    blocked = (section(path, "Blocked") or "(no Blocked section)") if status == "BLOCKED" else ""
    return BuildResult(status=status, blocked=blocked, agent=agent)
