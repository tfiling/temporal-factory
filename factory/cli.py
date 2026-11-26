"""Usage:
  python -m factory.cli queue                     start the queue: runs every issue labeled `factory`
  python -m factory.cli queue-status              jobs, stages and cost
  python -m factory.cli run <issue>               run one issue without the queue
  python -m factory.cli dry-run [base] [--json]   run the checks on up-to-date base in a throwaway worktree; waits
                                                  (--json: print {workflow_id, stage, job_dir, report} on stdout)
  ... [--flow <name>]                             any issue command: target a flow other than `implement`
  python -m factory.cli status <issue>
  python -m factory.cli merged <issue>            PR was merged by hand
  python -m factory.cli replied <issue>           nudge a needs-info job (the queue does this itself)
  echo "text" | python -m factory.cli feedback <issue>   send an escalated job back to the builder
  echo "why"  | python -m factory.cli reject <issue>     reject a job waiting for a human
(from Docker: docker compose run --rm -T worker python -m factory.cli ...)
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from temporalio.client import Client

from factory.core.models import ORCHESTRATION_QUEUE, DryRunInput, FlowName, QueueInput
from factory.flows.base import FactoryWorkflow
from factory.flows.queue import QUEUE_ID, FactoryQueueWorkflow
from factory.flows.registry import FLOWS, workflow_id

COMMANDS = {"run", "status", "merged", "replied", "feedback", "reject"}


async def main(argv: list[str]) -> None:
    flow = FlowName.IMPLEMENT
    as_json = argv[:1] == ["dry-run"] and "--json" in argv
    if as_json:
        argv = [a for a in argv if a != "--json"]
    if "--flow" in argv:
        i = argv.index("--flow")
        name, argv = (argv[i + 1] if i + 1 < len(argv) else ""), argv[:i] + argv[i + 2:]
        try:
            flow = FlowName(name)
        except ValueError:
            sys.exit(f"unknown flow {name!r}; flows: {', '.join(f.value for f in FlowName)}")
        if not FLOWS[flow].issue_driven:
            sys.exit(f"flow {flow.value!r} is not issue-driven; issue commands take: "
                     f"{', '.join(n.value for n, f in FLOWS.items() if f.issue_driven)}")
    if not (argv and ((len(argv) == 1 and argv[0] in {"queue", "queue-status"})
                      or (len(argv) == 2 and argv[0] in COMMANDS)
                      or (len(argv) <= 2 and argv[0] == "dry-run"))):
        sys.exit(__doc__)
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))
    if argv[0] == "dry-run":
        await dry_run(client, argv[1] if len(argv) == 2 else None, as_json)
        return
    if argv[0] == "queue":
        await client.start_workflow(FactoryQueueWorkflow.run, QueueInput(), id=QUEUE_ID,
                                    task_queue=ORCHESTRATION_QUEUE)
        print(f"started {QUEUE_ID}; watch it at http://localhost:8080")
        return
    if argv[0] == "queue-status":
        print(await client.get_workflow_handle(QUEUE_ID).query(FactoryQueueWorkflow.status))
        return
    cmd, issue = argv[0], int(argv[1])
    wf_id = workflow_id(flow, issue)
    handle = client.get_workflow_handle(wf_id)
    if cmd == "run":
        await client.start_workflow(FLOWS[flow].workflow.run, issue, id=wf_id, task_queue=ORCHESTRATION_QUEUE)
        print(f"started {wf_id}; watch it at http://localhost:8080")
    elif cmd == "status":
        print(await handle.query(FactoryWorkflow.status))
    elif cmd == "merged":
        await handle.signal(FactoryWorkflow.pr_merged)
    elif cmd == "replied":
        await handle.signal(FactoryWorkflow.author_replied)
    else:
        text = sys.stdin.read().strip()
        if not text:
            sys.exit(f"{cmd}: no text on stdin")
        await handle.signal(FactoryWorkflow.human_feedback if cmd == "feedback" else FactoryWorkflow.reject, text)
        print(f"sent {cmd} to {wf_id}")


async def dry_run(client: Client, base: str | None, as_json: bool = False) -> None:
    key = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    wf_id = workflow_id(FlowName.CI_DRY_RUN, key)
    handle = await client.start_workflow(FLOWS[FlowName.CI_DRY_RUN].workflow.run, DryRunInput(base, key), id=wf_id,
                                         task_queue=ORCHESTRATION_QUEUE)
    # With --json, stdout carries only the JSON result; progress goes to stderr.
    print(f"started {wf_id}; waiting (Ctrl-C leaves it running; watch it at http://localhost:8080)",
          file=sys.stderr if as_json else sys.stdout)
    stage = await handle.result()
    job_dir = (await handle.query(FactoryWorkflow.status))["job_dir"]
    report = f"{job_dir}/round-1/checks.md"
    if as_json:
        print(json.dumps({"workflow_id": wf_id, "stage": stage.value, "job_dir": job_dir, "report": report}))
    else:
        print(f"{stage.value}: see {report}")
    if stage != "passed":
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
