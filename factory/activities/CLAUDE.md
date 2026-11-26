# Activities
All IO lives here, grouped by domain. A gate FAIL or agent verdict is a return value, never an exception;
raise a non-retryable `ApplicationError` only for malformed agent output or input that can't succeed on retry
(e.g. `setup_job` on a closed or unlabeled issue).
- Register every new activity in `__init__.py` `ALL_BY_QUEUE` under its task queue; the worker registers only those.
- Activities are flow-agnostic: they take a `Job`/request dataclass and don't branch on the flow. Flow-specific
  behaviour comes from config or the prompt (`LabelChange.remove_flow_label` names a flow only to look up its label).
- Changing an activity's result dataclass: add fields with defaults so recorded histories still decode.
