import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from factory.activities import agents, gate, git, github, human, merge, routing
from factory.models import AGENTS_QUEUE, GIT_QUEUE, ORCHESTRATION_QUEUE
from factory.workflows.job import JobWorkflow
from factory.workflows.queue import FactoryQueueWorkflow


async def main() -> None:
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))
    with ThreadPoolExecutor(max_workers=16) as pool:
        workers = [
            Worker(client, task_queue=ORCHESTRATION_QUEUE, workflows=[JobWorkflow, FactoryQueueWorkflow],
                   activities=[routing.route_job], activity_executor=pool),
            Worker(client, task_queue=AGENTS_QUEUE,
                   activities=[agents.run_intake, agents.run_spec_writer, agents.run_builder,
                               agents.run_reviewer, agents.run_approver]),
            Worker(client, task_queue=GIT_QUEUE, activity_executor=pool,
                   activities=[github.setup_job, github.comment_issue, github.edit_labels,
                               github.ensure_pr, github.list_queue_issues, github.restart_intake,
                               git.create_worktree, git.verify_build, gate.run_gate,
                               merge.sync_and_merge, merge.cleanup_worktree,
                               human.escalate_job, human.write_feedback, human.reject_job]),
        ]
        await asyncio.gather(*(w.run() for w in workers))


if __name__ == "__main__":
    asyncio.run(main())
