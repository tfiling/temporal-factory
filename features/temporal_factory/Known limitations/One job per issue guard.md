---
type: known-limitation
status: open
created: 2026-11-26
tags: [queue, flows]
---

# One job per issue guard

`FactoryQueueWorkflow` blocks a second flow on an issue only while it tracks the first job (`self.jobs`).
- A job started with `cli run` has no parent and never reports, so after a relabel the queue can start another flow beside it.
- A job terminated from the UI sends no terminal state, so its entry stays: it blocks the issue under every flow and, unless it was waiting, holds a concurrency slot. `continue_as_new` carries it over, so only a terminal `job_state` signal sent by hand or a queue started from scratch clears it.
