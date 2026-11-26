"""The deterministic gate (ported from factory/bin/gate). A FAIL verdict is a value, not an error."""

import fnmatch
import time
from pathlib import Path

from temporalio import activity

from factory.core.config import load_config
from factory.core.models import GateRequest, GateResult
from factory.core.shell import run

TAIL = 80


def _protected_changes(worktree: str, base: str, patterns: list[str]) -> list[str]:
    diff = run(["git", "diff", "--name-status", f"origin/{base}...HEAD"], cwd=worktree).stdout
    hits = []
    for line in diff.splitlines():
        status, *paths = line.split("\t")
        if status.startswith("A"):
            continue
        if any(fnmatch.fnmatch(paths[0], p) for p in patterns):
            hits.append(f"{status[0]} {paths[0]}")
    return hits


@activity.defn
def run_gate(req: GateRequest) -> GateResult:
    return do_gate(req)


def do_gate(req: GateRequest) -> GateResult:
    cfg, job = load_config(), req.job
    name = "merge-checks" if req.merge else "checks"
    round_dir = Path(job.dir) / f"round-{req.round}"
    round_dir.mkdir(parents=True, exist_ok=True)
    commit = run(["git", "rev-parse", "HEAD"], cwd=job.worktree).stdout.strip()
    protected = _protected_changes(job.worktree, job.base, cfg.protected_paths)
    start = time.monotonic()
    res = run(["bash", "-c", cfg.checks_cmd], cwd=job.worktree, check=False)
    seconds = int(time.monotonic() - start)
    log = res.stdout + res.stderr
    verdict = "PASS" if res.returncode == 0 and not protected else "FAIL"
    (round_dir / f"{name}.log").write_text(log)
    tail = "\n".join(log.rstrip().splitlines()[-TAIL:])
    (round_dir / f"{name}.md").write_text(
        f"GATE: {verdict}\nCOMMIT: {commit}\n\n## Summary\n"
        f"- checks {'passed' if res.returncode == 0 else f'failed with exit {res.returncode}'} in {seconds}s\n"
        f"- Protected paths: {'changed: ' + ', '.join(protected) if protected else 'none changed'}\n"
        f"- Commit {commit[:7]}{', synced with the latest base before merging' if req.merge else ''}\n\n"
        f"## checks\nLast {TAIL} lines of {name}.log:\n\n```\n{tail}\n```\n"
    )
    return GateResult(verdict=verdict, commit=commit, exit_code=res.returncode, protected=protected)
