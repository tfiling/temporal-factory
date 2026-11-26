---
type: task
status: todo
created: 2026-11-27
tags: [bug, queue, cli, investigate]
related: "[[One job per issue guard]]"
---

# CLI reply leaves queue stage stale

## Suspected bug (not reproduced)
`wait_for_author` (`factory/flows/steps/intake.py`) calls `wf.notify()` when the job enters `needs-info`, but not after the author replies. When the queue relays the reply, it sets the job's entry to `resuming` itself (`factory/flows/queue.py`). When the reply is sent with `factory.cli replied <issue>`, nothing updates the queue.

**Possible failure:** a queue-started job resumed with `cli replied` stays `needs-info` in the queue's `self.jobs` while it runs intake, spec and build. It holds no concurrency slot, so the queue can go over `concurrency`, and `queue-status` shows the wrong stage until the job's next notify (needs-human or terminal).

## Investigate
- Confirm it with a queue test: a child in needs-info, `author_replied` sent directly to the child, then check the queue's `_working()` and `status`.
- A likely fix: `wf.notify()` after `restart_intake` in `wait_for_author`. This adds a signal command, so check the replay notes in `factory/flows/CLAUDE.md` (`workflow.patched`).
