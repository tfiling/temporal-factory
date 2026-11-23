"""Usage:
  python -m factory.cli queue                     start the queue: runs every issue labeled `factory`
  python -m factory.cli queue-status              jobs, stages and cost
  python -m factory.cli run <issue>               run one issue without the queue
  python -m factory.cli status <issue>
  python -m factory.cli merged <issue>            PR was merged by hand
  python -m factory.cli replied <issue>           nudge a needs-info job (the queue does this itself)
  echo "text" | python -m factory.cli feedback <issue>   send an escalated job back to the builder
  echo "why"  | python -m factory.cli reject <issue>     reject a job waiting for a human
(from Docker: docker compose run --rm -T worker python -m factory.cli ...)
"""

import asyncio
import os
import sys

from temporalio.client import Client

from factory.models import ORCHESTRATION_QUEUE, QueueInput
from factory.workflows.job import JobWorkflow
from factory.workflows.queue import QUEUE_ID, FactoryQueueWorkflow

COMMANDS = {"run", "status", "merged", "replied", "feedback", "reject"}


async def main(argv: list[str]) -> None:
    if not (argv and ((len(argv) == 1 and argv[0] in {"queue", "queue-status"})
                      or (len(argv) == 2 and argv[0] in COMMANDS))):
        sys.exit(__doc__)
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))
    if argv[0] == "queue":
        await client.start_workflow(FactoryQueueWorkflow.run, QueueInput(), id=QUEUE_ID,
                                    task_queue=ORCHESTRATION_QUEUE)
        print(f"started {QUEUE_ID}; watch it at http://localhost:8080")
        return
    if argv[0] == "queue-status":
        print(await client.get_workflow_handle(QUEUE_ID).query(FactoryQueueWorkflow.status))
        return
    cmd, issue = argv[0], int(argv[1])
    wf_id = f"factory-job-{issue}"
    handle = client.get_workflow_handle(wf_id)
    if cmd == "run":
        await client.start_workflow(JobWorkflow.run, issue, id=wf_id, task_queue=ORCHESTRATION_QUEUE)
        print(f"started {wf_id}; watch it at http://localhost:8080")
    elif cmd == "status":
        print(await handle.query(JobWorkflow.status))
    elif cmd == "merged":
        await handle.signal(JobWorkflow.pr_merged)
    elif cmd == "replied":
        await handle.signal(JobWorkflow.author_replied)
    else:
        text = sys.stdin.read().strip()
        if not text:
            sys.exit(f"{cmd}: no text on stdin")
        await handle.signal(JobWorkflow.human_feedback if cmd == "feedback" else JobWorkflow.reject, text)
        print(f"sent {cmd} to {wf_id}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
