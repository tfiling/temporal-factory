# Flows
A flow = one `@workflow.defn` class in `flows/<name>.py`, subclassing `FactoryWorkflow` (`base.py`),
composed from `steps/` (a small flow like `ci_dry_run.py` may call activities directly). Workflow code is
deterministic: no IO, no wall-clock time or random (use `workflow.now()`), only activities.

## Adding a flow
1. Note with a diagram in `features/temporal_factory/Flows/<Flow>.md` first; add it to the table in `Pipeline flow.md`.
2. `flows/<name>.py`: set `flow = FlowName.<NAME>`; `run()` sets state (e.g. `self.issue`) and returns `await self.reporting(self._run(...))`; `_run` calls steps. Keep it short.
3. Add a `FlowName` member (`core/models.py`), register it in `registry.py` (`FLOWS`: class, workflow id prefix, `issue_driven` = `run()` takes an `int` issue) and add `flows.<name>` to `config.json`
   (`label` makes the queue start it; first matching entry wins, so list specific flows before `implement`; only issue-driven flows may have a `label`).
4. Tests in `tests/test_<name>_flow.py` with mocked activities (see `tests/test_implement_flow.py`).

## Rules
- Shared state, signals, query, `notify`/`finish` live only in `base.py`; flows don't redefine them.
- Reuse steps; when a flow needs a variant, parametrize the step rather than copying it.
- New stages go in the shared `Stage` enum (`core/models.py`); add them to the queue's WAITING or TERMINAL set if they are.
- Pass through (`workflow.unsafe.imports_passed_through()`) only `factory.activities.*` and `factory.core.*`; import
  other flow modules normally so the sandbox checks them. It doesn't check passed-through code: from activities take
  only activity references, from core only types and pure functions.
- Don't change the activity order of an existing flow or step without a `workflow.patched` gate: waiting runs
  must replay. `implement` keeps type name `JobWorkflow`, id `factory-job-<issue>` and its `int` input.
