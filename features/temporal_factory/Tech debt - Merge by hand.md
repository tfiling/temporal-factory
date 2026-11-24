---
type: tech-debt
status: open
created: 2026-11-24
tags: [tech-debt, queue, github]
---

# Tech debt: PRs merged on GitHub are not detected

## Today
When a job escalates to `needs-human`, it waits for a `feedback`, `reject` or `merged` signal. If a person merges the PR on GitHub, nothing signals the workflow, so the job stays in `needs-human` until someone runs `factory.cli merged <issue>`.

## Impact
Jobs merged by hand sit in `needs-human` forever, still count against queue state, and show the wrong status in `queue-status`.

## Options
- Have the queue workflow check PR state for waiting jobs on each 60s poll and signal `merged`. This matches v2's job queue, which checked PR state on every pass.
- Add a GitHub webhook that signals the job when its PR is merged.

## Status
Open. Workaround: `factory.cli merged <issue>`.
