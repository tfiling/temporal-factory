"""Activity options shared by every flow."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from factory.core.models import AGENTS_QUEUE, GIT_QUEUE

GIT = dict(task_queue=GIT_QUEUE, start_to_close_timeout=timedelta(minutes=5),
           retry_policy=RetryPolicy(maximum_attempts=5, backoff_coefficient=2.0))
GATE = dict(task_queue=GIT_QUEUE, start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=2))
MERGE = dict(task_queue=GIT_QUEUE, start_to_close_timeout=timedelta(minutes=45),
             retry_policy=RetryPolicy(maximum_attempts=2))  # idempotent: checks PR state first


def agent_opts(timeout_minutes: int) -> dict:
    return dict(task_queue=AGENTS_QUEUE, start_to_close_timeout=timedelta(minutes=timeout_minutes),
                heartbeat_timeout=timedelta(minutes=3), retry_policy=RetryPolicy(maximum_attempts=2))
