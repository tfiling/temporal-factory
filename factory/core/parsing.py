"""Readers for the markdown files agents write (ported from factory/bin/job in the v2 example)."""

import re
from pathlib import Path


def first_line(path: Path) -> str | None:
    return path.read_text().split("\n", 1)[0].strip() if path.exists() else None


# noinspection DuplicatedCode  - 1:1 port of the header() in examples/software-factory-claude-code-v2/factory/bin/job
def header(path: Path) -> dict[str, str]:
    """KEY: value lines at the top of a file, up to the first blank line."""
    fields = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            break
        key, _, value = line.partition(":")
        fields[key.strip().upper()] = value.strip()
    return fields


def section(path: Path, heading: str) -> str | None:
    """Body of a `## heading` section, or None."""
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", path.read_text(), re.M | re.S)
    return m.group(1).strip() if m else None


def body_after_header(path: Path) -> str:
    parts = path.read_text().split("\n\n", 1)
    return parts[1].strip() if len(parts) > 1 else ""
