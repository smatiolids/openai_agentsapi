"""Persistent command-history file (~/.openai_agents_history)."""

from __future__ import annotations

from pathlib import Path

_DEFAULT_PATH = Path.home() / ".openai_agents_history"
_MAX_LINES = 1000  # cap to avoid unbounded growth


def load(path: Path = _DEFAULT_PATH) -> list[str]:
    """Return history entries from *path*, oldest first. Missing file → []."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    # Strip blanks; keep the last MAX_LINES entries
    return [l for l in lines if l.strip()][-_MAX_LINES:]


def append(entry: str, path: Path = _DEFAULT_PATH) -> None:
    """Append a single *entry* to the history file, creating it if needed."""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry.rstrip("\n") + "\n")
