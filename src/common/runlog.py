"""Append one entry per run to RUNLOG.md (project rule 7)."""
from __future__ import annotations

import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def commit() -> str:
    return _git("rev-parse", "HEAD") or "no-commit"


def dirty() -> bool:
    return bool(_git("status", "--porcelain"))


def append(command: str, duration_s: float, output: str, status: str = "ok",
           note: str = "", path: Path | None = None) -> None:
    path = path or ROOT / "RUNLOG.md"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sha = commit()[:12] + ("+dirty" if dirty() else "")
    note = note.replace("|", "/").replace("\n", " ")
    line = f"| {stamp} | `{command}` | {sha} | {duration_s:.1f}s | {output} | {status} | {note} |\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)


@contextmanager
def logged(command: str, output: str, note: str = ""):
    """Time a run and log it whether it succeeds or fails."""
    start = time.time()
    try:
        yield
    except BaseException as exc:
        append(command, time.time() - start, output, status="FAILED", note=f"{type(exc).__name__}: {exc}"[:200])
        raise
    append(command, time.time() - start, output, note=note)
