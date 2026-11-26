import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from factory.activities import ALL_BY_QUEUE
from factory.core.config import load_config
from factory.core.models import ORCHESTRATION_QUEUE
from factory.flows.queue import FactoryQueueWorkflow
from factory.flows.registry import FLOWS, config_errors


async def main() -> None:
    if errors := config_errors(load_config().flows):
        raise SystemExit("\n".join(errors))
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))
    workflows = [FactoryQueueWorkflow, *(f.workflow for f in FLOWS.values())]
    with ThreadPoolExecutor(max_workers=16) as pool:
        workers = [Worker(client, task_queue=queue, activities=acts, activity_executor=pool,
                          workflows=workflows if queue == ORCHESTRATION_QUEUE else [])
                   for queue, acts in ALL_BY_QUEUE.items()]
        await asyncio.gather(*(w.run() for w in workers))


if __name__ == "__main__":
    asyncio.run(main())
