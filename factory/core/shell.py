import subprocess


def run(cmd: list[str], cwd=None, check: bool = True) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"`{' '.join(cmd)}` failed: {res.stderr.strip() or res.stdout.strip()}")
    return res
