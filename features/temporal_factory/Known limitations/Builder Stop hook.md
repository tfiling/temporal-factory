---
type: known-limitation
status: open
created: 2026-11-24
tags: [limitations, builder, gate]
---

# Known limitation: builder Stop hook not ported

## Limitation
In v2, a Stop hook on the builder ran the checks before the builder could finish. That hook was not ported, so the gate runs only after the builder activity returns.

## Impact
A builder that leaves failing checks costs a full round (gate FAIL, then a new build) instead of being fixed within the same agent session. More rounds mean more cost and an earlier `needs-human`.

## Options
- Port the Stop hook into the builder's Claude Agent SDK session, running the checks command (`FACTORY_CHECKS_CMD`) and blocking the stop on failure.
- Keep the gate as the authoritative check either way, since a FAIL is a return value the workflow already handles.

## Decision
Open.
