"""JobWorkflow: one GitHub issue → merged PR.

intake → route → spec → [build → gate → review]* → approve → merge, with escalation to a human
(signals: human_feedback, reject, pr_merged). Ported from the v2 state machine in factory/bin/job.
Keep features/temporal_factory/Pipeline flow.md in sync with any change here.
"""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import TemporalError

with workflow.unsafe.imports_passed_through():
    from factory.activities.agents import (run_approver, run_builder, run_intake, run_reviewer,
                                           run_spec_writer)
    from factory.activities.gate import run_gate
    from factory.activities.git import create_worktree, verify_build
    from factory.activities.github import comment_issue, edit_labels, ensure_pr, restart_intake, setup_job
    from factory.activities.human import escalate_job, reject_job, write_feedback
    from factory.activities.merge import cleanup_worktree, sync_and_merge
    from factory.activities.routing import route_job
    from factory.models import (AGENTS_QUEUE, GIT_QUEUE, AgentRequest, Comment, EscalateArgs,
                                GateRequest, JobState, LabelChange, MergeRequest, Stage, TextArgs)

GIT = dict(task_queue=GIT_QUEUE, start_to_close_timeout=timedelta(minutes=5),
           retry_policy=RetryPolicy(maximum_attempts=5, backoff_coefficient=2.0))
GATE = dict(task_queue=GIT_QUEUE, start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=2))
MERGE = dict(task_queue=GIT_QUEUE, start_to_close_timeout=timedelta(minutes=45),
             retry_policy=RetryPolicy(maximum_attempts=2))  # idempotent: checks PR state first


def agent_opts(timeout_minutes: int) -> dict:
    return dict(task_queue=AGENTS_QUEUE, start_to_close_timeout=timedelta(minutes=timeout_minutes),
                heartbeat_timeout=timedelta(minutes=3), retry_policy=RetryPolicy(maximum_attempts=2))


@workflow.defn
class JobWorkflow:
    def __init__(self) -> None:
        self.stage: Stage = Stage.STARTING
        self.round = 0
        self.issue = 0
        self.waits = 0
        self.pr_url: str | None = None
        self.pr_number: int | None = None
        self.cost_usd = 0.0
        self._session: str | None = None
        self._feedback: list[str] = []
        self._rejection: str | None = None
        self._merged = False
        self._replied = False

    @workflow.query
    def status(self) -> dict:
        return {"stage": self.stage, "round": self.round, "waits": self.waits,
                "pr_url": self.pr_url, "cost_usd": self.cost_usd}

    # Signals are only consumed while the job waits in needs-human.
    @workflow.signal
    def author_replied(self) -> None:
        self._replied = True

    @workflow.signal
    def human_feedback(self, text: str) -> None:
        self._feedback.append(text)

    @workflow.signal
    def reject(self, reason: str) -> None:
        self._rejection = reason

    @workflow.signal
    def pr_merged(self) -> None:
        self._merged = True

    async def _notify(self, stage: Stage | None = None) -> None:
        """Tell the parent queue (if any) whether this job is working, waiting or done."""
        parent = workflow.info().parent
        if parent is None:
            return
        try:
            await workflow.get_external_workflow_handle(parent.workflow_id).signal(
                "job_state", JobState(self.issue, stage or self.stage, self.cost_usd))
        except TemporalError:
            pass  # the queue isn't running; the job doesn't depend on it

    async def _finish(self, job, stage: Stage) -> Stage:
        await workflow.execute_activity(cleanup_worktree, job, **GIT)
        self.stage = stage
        return stage

    async def _wait_for_human(self, job, why: str, rnd: int, write_decision: bool = True) -> tuple[Stage | None, str]:
        """Escalate and wait. Returns (terminal stage, "") or (None, message for the next build round)."""
        await workflow.execute_activity(
            escalate_job, EscalateArgs(job, why, self.pr_number, write_decision), **GIT)
        self.stage, self.waits = Stage.NEEDS_HUMAN, self.waits + 1
        await self._notify()
        await workflow.wait_condition(lambda: bool(self._feedback) or self._rejection is not None or self._merged)
        if self._merged:
            await workflow.execute_activity(edit_labels, LabelChange(job.issue, remove=["needs_human"]), **GIT)
            return await self._finish(job, Stage.MERGED), ""
        if self._rejection is not None:
            await workflow.execute_activity(reject_job, TextArgs(job, self._rejection, self.pr_number), **GIT)
            return await self._finish(job, Stage.REJECTED), ""
        self.stage = Stage.BUILD
        await self._notify()
        text, self._feedback = "\n\n".join(self._feedback), []
        k = await workflow.execute_activity(write_feedback, TextArgs(job, text), **GIT)
        return None, (f"Round {rnd + 1}. The job escalated and a human sent feedback: read feedback-{k}.md, "
                      f"decision.md and every round folder first.")

    async def _round(self, job, reviewers: dict, rnd: int, message: str):
        """One build → gate → review round. Returns (kind, message, why):
        reviewed | retry (message for the next round, why if none is left) | escalate (why)."""
        self.stage = Stage.BUILD
        build = await workflow.execute_activity(
            run_builder, AgentRequest(job, "builder", message, round=rnd, session_id=self._session), **agent_opts(60))
        self.cost_usd += build.agent.cost_usd
        self._session = build.agent.session_id or self._session
        if build.status == "BLOCKED":
            return "escalate", "", f"The builder is blocked:\n\n{build.blocked}"
        if problem := await workflow.execute_activity(verify_build, job, **GIT):
            return "escalate", "", f"The build can't be gated: {problem}"

        self.stage = Stage.GATE
        gate = await workflow.execute_activity(run_gate, GateRequest(job, rnd), **GATE)
        if gate.verdict != "PASS":
            return ("retry",
                    f"Round {rnd + 1}. The gate failed in round {rnd}: read round-{rnd}/checks.md and "
                    f"checks.log in the job folder, then fix it.",
                    f"The gate failed in round {rnd}, the last allowed round (see round-{rnd}/checks.md).")

        if not self.pr_number:
            pr = await workflow.execute_activity(ensure_pr, job, **GIT)
            self.pr_url, self.pr_number = pr.url, pr.number

        self.stage = Stage.REVIEW
        reviews = await asyncio.gather(*(
            workflow.execute_activity(
                run_reviewer, AgentRequest(job, f"reviewer-{lens}", f"Review round {rnd}.", round=rnd, model=model),
                **agent_opts(30))
            for lens, model in reviewers.items()))
        self.cost_usd += sum(r.cost_usd for r in reviews)
        changes = ", ".join(r.lens for r in reviews if r.verdict == "CHANGES")
        if not changes:
            return "reviewed", "", ""
        return ("retry",
                f"Round {rnd + 1}. Reviews asked for changes: address each finding in "
                f"round-{rnd}/review-<lens>.md for {changes}.",
                f"Review rounds exhausted. Outstanding CHANGES in round-{rnd}/ from: {changes}.")

    @workflow.run
    async def run(self, issue: int) -> Stage:
        self.issue = issue
        try:
            stage = await self._run(issue)
        except Exception:
            await self._notify(Stage.FAILED)
            raise
        await self._notify(stage)
        return stage

    async def _run(self, issue: int) -> Stage:
        job = await workflow.execute_activity(setup_job, issue, **GIT)
        intake = await self._intake(job)
        if intake is None:  # rejected while waiting for the author
            return await self._finish(job, Stage.REJECTED)
        if intake.decision == "REJECT":
            return await self._reject_at_intake(job, intake)
        reviewers = await self._prepare(job, intake)
        return await self._build_rounds(job, reviewers)

    @staticmethod
    def _intake_comment(intake) -> str:
        return f"### Factory intake: {intake.decision}\n\n{intake.body}"

    async def _intake(self, job):
        """Run intake, asking the author for info until it decides. Returns None if rejected meanwhile."""
        while True:  # intake repeats after each author reply
            self.stage = Stage.INTAKE
            intake = await workflow.execute_activity(
                run_intake, AgentRequest(job, "intake", "Decide this issue and write intake.md."), **agent_opts(15))
            self.cost_usd += intake.agent.cost_usd
            if intake.decision != "NEEDS-INFO":
                return intake
            if not await self._wait_for_author(job, intake):
                return None

    async def _wait_for_author(self, job, intake) -> bool:
        """Ask the author for info and wait. Returns False if the job was rejected instead."""
        await workflow.execute_activity(comment_issue, Comment(job.issue, self._intake_comment(intake)), **GIT)
        await workflow.execute_activity(edit_labels, LabelChange(job.issue, add=["needs_info"]), **GIT)
        self.stage, self.waits = Stage.NEEDS_INFO, self.waits + 1
        await self._notify()
        await workflow.wait_condition(lambda: self._replied or self._rejection is not None)
        if self._rejection is not None:
            await workflow.execute_activity(reject_job, TextArgs(job, self._rejection), **GIT)
            return False
        self._replied = False
        await workflow.execute_activity(restart_intake, job, **GIT)
        return True

    async def _reject_at_intake(self, job, intake) -> Stage:
        await workflow.execute_activity(comment_issue, Comment(job.issue, self._intake_comment(intake)), **GIT)
        await workflow.execute_activity(edit_labels, LabelChange(job.issue, remove=["queue"]), **GIT)
        self.stage = Stage.REJECTED
        return self.stage

    async def _prepare(self, job, intake) -> dict:
        """Route, announce intake, create the worktree and write the spec. Returns the reviewers."""
        reviewers = await workflow.execute_local_activity(
            route_job, intake, start_to_close_timeout=timedelta(seconds=10))
        await workflow.execute_activity(comment_issue, Comment(job.issue, self._intake_comment(intake)), **GIT)
        await workflow.execute_activity(create_worktree, job, **GIT)

        self.stage = Stage.SPEC
        spec = await workflow.execute_activity(
            run_spec_writer, AgentRequest(job, "spec-writer", "Write spec.md."), **agent_opts(30))
        self.cost_usd += spec.cost_usd
        return reviewers

    async def _build_rounds(self, job, reviewers: dict) -> Stage:
        """Build rounds until merged or a human ends the job; human feedback restarts the round budget."""
        message, rnd, limit = "Build the spec.", 0, job.max_rounds
        while True:
            rnd += 1
            self.round = rnd
            kind, next_message, why = await self._round(job, reviewers, rnd, message)
            if kind == "retry" and rnd < limit:
                message = next_message
                continue

            write_decision = True
            if kind == "reviewed":
                merged, why, write_decision = await self._approve_and_merge(job, rnd)
                if merged:
                    return await self._finish(job, Stage.MERGED)
            # else: escalate now, or a retry with no rounds left
            stage, message = await self._wait_for_human(job, why, rnd, write_decision)
            if stage:
                return stage
            limit = rnd + job.max_rounds

    async def _approve_and_merge(self, job, rnd: int) -> tuple[bool, str, bool]:
        """Returns (merged, why not, approved)."""
        self.stage = Stage.APPROVE
        decision = await workflow.execute_activity(
            run_approver,
            AgentRequest(job, "approver", f"PR: #{self.pr_number} {self.pr_url}. Final round: {rnd}.", round=rnd),
            **agent_opts(30))
        self.cost_usd += decision.agent.cost_usd
        if decision.decision != "APPROVE":
            return False, decision.body, False

        self.stage = Stage.MERGING
        merge = await workflow.execute_activity(sync_and_merge, MergeRequest(job, self.pr_number, rnd), **MERGE)
        return merge.merged, merge.detail, True
