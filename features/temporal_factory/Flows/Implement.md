---
type: architecture
status: current
created: 2026-11-23
tags: [architecture, pipeline, diagram, flow]
related: "[[Pipeline flow]]"
---

# Implement flow

`ImplementWorkflow` (`factory/flows/implement.py`, Temporal type `JobWorkflow`, id `factory-job-<issue>`): one GitHub issue becomes a merged PR. Issues labeled `factory` run it (config `flows.implement.label`). It only composes shared steps from `factory/flows/steps/` (see [[Pipeline flow#Shared steps]]).

## Stages

```mermaid
flowchart TD
    issue([GitHub issue labeled factory]) --> trigger{{"cli run &lt;n&gt; or FactoryQueueWorkflow<br/>queue: up to concurrency working jobs"}}
    trigger --> setup[setup_job<br/>clone repo if missing, check issue open + labeled, issue.md]
    setup --> intake[/"Intake agent (Opus)<br/>writes intake.md"/]
    intake -->|NEEDS-INFO| ask[comment + needs-info label]
    ask -->|"author_replied signal<br/>(CLI replied, or the queue on an author reply)"| restart[restart_intake] --> intake
    ask -->|reject signal| rejected([rejected])
    intake -->|REJECT| rejected
    intake -->|ACCEPT| route[route_job, local activity<br/>risk + surfaces to reviewers]
    route --> wt[comment_issue + create_worktree]
    wt --> spec[/"Spec writer agent (Opus)<br/>writes spec.md"/]
    spec --> round

    subgraph round [Round: repeats up to max_rounds]
        build[/"Builder agent (Opus)<br/>commits, pushes, build.md"/] --> verify[verify_build]
        verify --> gate[run_gate<br/>checks_cmd + protected paths]
        gate -->|PASS| pr[ensure_pr<br/>draft PR, once: first round whose gate passes]
        pr --> reviews[/"Reviewer agents in parallel<br/>round-N/review-&lt;lens&gt;.md"/]
    end

    build -->|BLOCKED| human
    verify -->|problem| human
    gate -->|FAIL, rounds left| build
    reviews -->|CHANGES, rounds left| build
    gate -->|FAIL, no rounds left| human
    reviews -->|CHANGES, no rounds left| human
    reviews -->|all PASS| approver[/"Approver agent (Opus)<br/>decision.md"/]
    approver -->|ESCALATE| human
    approver -->|APPROVE| merge[sync_and_merge<br/>merge main, merge-checks, gh pr merge]
    merge -->|merged| merged([merged])
    merge -->|conflict / gate fail / push or merge error| human

    human{{"needs-human<br/>escalate_job, wait for signal"}}
    human -->|feedback signal<br/>round budget resets| build
    human -->|reject signal| rejected
    human -->|pr_merged signal| merged
```

Parallelograms are Claude agents (Claude Agent SDK, prompts in `factory/prompts/`). Rectangles are deterministic activities.

- **Trigger:** `FactoryQueueWorkflow` (`factory/flows/queue.py`) starts a job per labeled issue while fewer than `concurrency` jobs are working (`config.json`, default 3; waiting jobs don't count), and never while it tracks an open job for the issue under any flow. It also signals `author_replied` to needs-info jobs whose author (or the operator) replied, while under the cap.
- **Cleanup:** every terminal stage reached after the worktree exists (merged via `sync_and_merge` or `pr_merged`, rejected from needs-human) runs `cleanup_worktree` through `FactoryWorkflow.finish`. The intake REJECT path returns before the worktree exists and runs no cleanup; a needs-info reject also happens before the worktree exists (its `finish` cleanup is a no-op apart from `git branch -D`).
- **Intake REJECT** comments and removes the flow's trigger label (`flows.implement.label`, resolved by `edit_labels` from `LabelChange.remove_flow_label`, a `FlowName`; nothing is removed if the flow has no entry or label), not `labels.queue`.
- `route_job` runs as a local activity and raises if intake's risk or a surface isn't in `config.json` (raised in `route()`, `factory/core/routing.py`).
- The workflow fails (and reports `failed` to the queue) when an activity raises after its retries, e.g. `setup_job` on a closed or unlabeled issue or malformed agent output.

## Reviewer routing

`route_job` (`factory/activities/routing.py`, calling `route()` in `factory/core/routing.py`) builds the reviewer set from intake's `RISK` and `SURFACES` using `factory/config.json`.

```mermaid
flowchart LR
    risk{RISK} -->|low| c1[code: haiku]
    risk -->|medium / high| c2[code: sonnet]
    surf{SURFACES} -->|ui| ux[ux: sonnet] & ui[ui: haiku]
    surf -->|security| sec[security: opus]
    c1 & c2 & ux & ui & sec --> set[(reviewer set)]
```

## Job folder artifacts


| File | Written by |
|---|---|
| `issue.md` | `setup_job` / `restart_intake` |
| `intake.md` | intake agent |
| `spec.md` | spec writer |
| `build.md` | builder |
| `round-N/checks.md`, `checks.log` | `run_gate` |
| `round-N/review-<lens>.md` | reviewers |
| `decision.md` | approver; `escalate_job` on every other escalation (a failed merge overwrites the approver's `APPROVE`) |
| `round-N/merge-checks.md`, `merge-checks.log` | `sync_and_merge` (re-runs the gate) |
| `feedback-K.md` | `write_feedback` |
| `rejection.md` | `reject_job` |
| `intake-K.md` | `restart_intake` (archives the previous `intake.md`) |
