# Steps
Reusable workflow fragments: `async def step(wf: FactoryWorkflow, job, ...)`, shared by flows.
- Deterministic; call activities with the options in `flows/options.py` (the local `route_job` sets its own timeout).
- Steps update `wf.stage`, `wf.cost_usd`, `wf.round`, `wf.pr_*`; flows sequence steps (a flow without steps, like
  `ci_dry_run.py`, sets them itself).
- Expected outcomes (gate FAIL, review CHANGES, rejection, escalation) are return values, never exceptions.
- Every step module is used by at least one flow and covered by that flow's tests.
