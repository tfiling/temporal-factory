---
type: architecture
status: current
created: 2026-11-23
tags: [architecture, pipeline, diagram]
---

# Pipeline flow

The current `JobWorkflow` pipeline (`factory/workflows/job.py`): one GitHub issue becomes a merged PR.

## Stages

```mermaid
flowchart TD
    issue([GitHub issue labeled factory]) --> trigger{{"cli run &lt;n&gt; or FactoryQueueWorkflow<br/>queue: up to concurrency working jobs"}}
    trigger --> setup[setup_job<br/>clone repo, issue.md]
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
        gate -->|PASS| pr[ensure_pr<br/>draft PR, first round only]
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

- **Trigger:** `FactoryQueueWorkflow` (`queue.py`) starts a job per labeled issue while fewer than `concurrency` jobs are working (`config.json`, default 3; waiting jobs don't count). It also signals `author_replied` to needs-info jobs whose author replied.
- **Cleanup:** every terminal stage reached after the worktree exists (merged via `sync_and_merge` or `pr_merged`, rejected from needs-human) runs `cleanup_worktree` through `_finish`. The intake REJECT path returns before the worktree exists and runs no cleanup; a needs-info reject also happens before the worktree exists (its `_finish` cleanup is a no-op apart from `git branch -D`).
- `route_job` runs as a local activity and raises if intake's risk or a surface isn't in `config.json` (`routing.py`).

## Reviewer routing

`route_job` (`factory/routing.py`) builds the reviewer set from intake's `RISK` and `SURFACES` using `factory/config.json`.

```mermaid
flowchart LR
    risk{RISK} -->|low| c1[code: haiku]
    risk -->|medium / high| c2[code: sonnet]
    surf{SURFACES} -->|ui| ux[ux: sonnet] & ui[ui: haiku]
    surf -->|security| sec[security: opus]
    c1 & c2 & ux & ui & sec --> set[(reviewer set)]
```

## Components and task queues

```mermaid
flowchart LR
    cli[factory.cli] -->|start / signal / query| temporal[(Temporal server)]
    ui[Temporal UI :8080] --- temporal
    temporal --- orch

    subgraph worker [worker container]
        orch["orchestration queue<br/>JobWorkflow, FactoryQueueWorkflow, route_job"]
        agents["agents queue<br/>intake, spec-writer, builder, reviewer, approver"]
        git["git queue<br/>setup_job, comment_issue, edit_labels, ensure_pr, list_queue_issues,<br/>restart_intake, create_worktree, verify_build, run_gate,<br/>sync_and_merge, cleanup_worktree,<br/>escalate_job, write_feedback, reject_job"]
    end

    orch --> agents & git
    agents -->|Agent SDK| claude[(Claude API)]
    git -->|gh CLI| github[(GitHub target repo)]
    agents & git --> data[("/data volume<br/>repo/, repo/.worktrees/id, jobs/id/")]
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
| `decision.md` | approver (or `escalate_job`) |
| `round-N/merge-checks.md` | `sync_and_merge` |
| `feedback-K.md` | `write_feedback` |
| `rejection.md` | `reject_job` |
| `intake-K.md` | `restart_intake` (archives the previous `intake.md`) |
