---
status: todo
---

# Agent prompt fixes

Source: Zavik review of `factory/prompts/` against the flows that use them (2026-11-26). Code-reading only; nothing was run. The verdict-line formats in all prompts already match what `agents.py` parses.

## Confirmed

- **C1 Location model.** `spec-writer.md:8-12`, `builder.md:9-15`, `approver.md:15-19` and `reviewer-*.md:9-13` say the job folder is "in the main checkout". In reality the job folder is `/data/jobs/<id>` (`github.py:79`), the repo is `/data/repo` (`github.py:35`), and every agent except intake starts in the worktree (`agents.py:40`). "Never edit the main checkout: it belongs to the user" (`builder.md:14-15`) doesn't hold, because the checkout is a private clone.
- **C2 `protected_paths` unreachable.** `spec-writer.md:75-76` and `builder.md:46-47` point at `factory/config.json`, which lives at `/app/...` (`config.py:47`), outside the worktree and `add_dirs` (`agents.py:41`). The values aren't in the job header either.
- **C3 No browser.** `builder.md:63-70`, `reviewer-ux.md:27-37` and `reviewer-ui.md:29-39` require `agent-browser` and `lsof`. The Dockerfile installs neither (`Dockerfile:4`; see Known limitations). Agents waste time until the timeout, or claim they saw a page they never rendered.
- **C4 One-line `decision.md` crashes.** `split("\n", 1)[1]` (`agents.py:98`) raises IndexError when the file is only `APPROVE`. The error is retryable, so a full approver run is paid for again.
- **C5 SURFACES/RISK not normalised.** There is no `.lower()` on SURFACES (`agents.py:66`), and `route()` raises on unknown values (`routing.py:7-12`). `intake.md:49` doesn't require exact lowercase values.
- **C6 Wrong `checks.log` path.** `builder.md:23-24` say the job folder, and the retry message (`build.py:40-41`) names `round-N/checks.md` but gives `checks.log` without the round folder; the real path is `round-N/checks.log` (`gate.py:45`).
- **L3 Operator note left in the prompt.** `approver.md:49` ("Tailor these lists to the project…") is addressed to the operator, and the agent may act on it.

## Plausible

- **C7** A code fence or blank first line in the output file breaks `first_line`/`header` (`parsing.py:8,14-16`). All templates are shown inside ```` ```markdown ```` blocks.
- **C8** `RESCOPED` is parsed (`agents.py:68`) but nothing consumes it.
- **E1** A builder retry resumes the previous round's session (`build.py:28`). Partial uncommitted work may be left in the worktree, and the prompt never says to check `git status`.
- **E2** "In round 1, run the setup" (`builder.md:37`) is ambiguous for later rounds; better: "if dependencies are not installed".
- **E3** The builder is never told to merge `origin/<base>` after a conflict is reported; `merge.py:26-28` aborts and escalates. "Resolving merge conflicts" (`builder.md:42-43`) is a leftover from the example.
- **E4** The security, ux and ui reviewers lack the "Checks are done" section (`reviewer-code.md:26-31`), so they may rerun the checks.
- **E5** Reviewers and the approver have Write and Bash under `bypassPermissions`. A stray edit leaves the worktree dirty, and nothing verifies a clean tree before `sync_and_merge`.
- **E6** The issue title (`github.py:47`) is outside the quoted block and flows into the spec and PR title, a small injection vector.
- **E7** Intake's repo is cloned once and never fetched (`github.py:35-39`), so intake judges scope against a stale main. This is a code issue, not a prompt issue.
- **E8** The approver escalates on any new dependency (`approver.md:45`), even after the security reviewer passed it. Probably intended, but not documented.
- **L6** Cosmetic: lowercase sentence starts left over from `$CHECKS` substitution (`spec-writer.md:72`, `reviewer-code.md:28`).

## Plan (by impact)

- [ ] 1. Rewrite "Where you work" in all prompts: "You start in the worktree (`Worktree:` in your header). The job folder (`Job folder:`) is a separate directory outside the repo; write your one file there by its absolute path." Remove every mention of "main checkout". (C1)
- [ ] 2. Add to every output template: "Write the file raw: no code fence, nothing before the first line." (C7)
- [ ] 3. In intake: RISK is exactly `low|medium|high`; SURFACES is exactly `none` or a comma list of `ui`, `security`, all lowercase. Add `.lower()` in `agents.py:66`. (C5)
- [ ] 4. Inject `Protected paths: …` into `job_header` (`agents.py:29-31`) and reference that in the prompts. (C2)
- [ ] 5. While the browser limitation is open, replace the browser sections: "There is no browser here. Judge from code, styles and markup; say in Notes that nothing was rendered. Never claim you saw a page." (C3)
- [ ] 6. Delete `approver.md:49`, require at least `## Why` below the first line, and use `partition("\n")[2]` in `agents.py:98`. (C4, L3)
- [ ] 7. Fix the `checks.log` path in `builder.md:23-24` and `build.py:40-41`. (C6)
- [ ] 8. Builder: start with `git status` and handle interrupted work deliberately; if feedback or decision.md mentions a base conflict, merge `origin/<base>` and resolve it. (E1, E3)
- [ ] 9. Copy "Checks are done" into the security, ux and ui reviewer prompts. (E4)
- [ ] 10. Reviewers and approver: "the worktree must be clean when you finish". Consider running `verify_build` before `sync_and_merge`. (E5)

## Verification

Unit tests with mocked activities, each expected to fail today:
- `decision.md` containing only `APPROVE`
- `intake.md` with `SURFACES: UI`
- `review-code.md` starting with ```` ```markdown ````

Per CLAUDE.md, update `Flows/` notes and `Pipeline flow.md` for any change to job artifacts or shared steps.
