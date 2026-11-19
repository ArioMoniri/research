#!/usr/bin/env python3
"""Block data, dumps, credentials and patient identifiers from entering git.

    python scripts/precommit_check.py            # staged files (pre-commit)
    python scripts/precommit_check.py --all      # every tracked file (before a push)

Blocks: files over 5 MB; Parquet and similar columnar files; CSV/TSV outside
results/ (PROVENANCE.csv and tests/fixtures/ excepted); database dumps; wallet
and credential files; any text matching a patient-ID pattern in
configs/patient_id_patterns.txt; any valid Turkish national ID number.
Standard library only, so it runs in a fresh clone.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

MAX_BYTES = 5 * 1024 * 1024
COLUMNAR = {".parquet", ".pq", ".feather", ".arrow", ".orc", ".avro"}
TABULAR = {".csv", ".tsv"}
DUMPS = {".dmp", ".dump", ".bak", ".expdp", ".backup", ".mdf", ".ldf", ".bacpac", ".sqlite", ".db"}
DUMP_SUFFIXES = (".sql.gz", ".sql.zip", ".sql.bz2", ".dmp.gz")
CREDENTIAL_NAMES = {"cwallet.sso", "ewallet.p12", "tnsnames.ora", "sqlnet.ora", ".env", ".pgpass"}
TABULAR_ALLOWED_PREFIXES = ("results/", "tests/fixtures/")
TABULAR_ALLOWED_FILES = {"PROVENANCE.csv"}
# This file and its tests contain the patterns themselves.
SCAN_EXEMPT = {"scripts/precommit_check.py", "tests/test_precommit.py", "configs/patient_id_patterns.txt"}
TCKN = re.compile(r"(?<![\d.])[1-9]\d{10}(?!\d)")


def valid_tckn(s: str) -> bool:
    """Checksum of the 11-digit Turkish national ID number."""
    d = [int(c) for c in s]
    if len(d) != 11 or d[0] == 0:
        return False
    if ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


def load_patterns(root: Path) -> list[re.Pattern]:
    path = root / "configs" / "patient_id_patterns.txt"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(re.compile(line))
    return out


def check_path(rel: str, size: int) -> list[str]:
    p = PurePosixPath(rel)
    name, ext, problems = p.name.lower(), p.suffix.lower(), []
    if size > MAX_BYTES:
        problems.append(f"file is {size / 1e6:.1f} MB (limit 5 MB)")
    if ext in COLUMNAR:
        problems.append("columnar data file")
    if ext in TABULAR and p.name not in TABULAR_ALLOWED_FILES and not rel.startswith(TABULAR_ALLOWED_PREFIXES):
        problems.append("CSV/TSV outside results/")
    if ext in DUMPS or name.endswith(DUMP_SUFFIXES):
        problems.append("database dump or database file")
    if name in CREDENTIAL_NAMES or ext in {".sso", ".p12", ".jks", ".pem", ".key"}:
        problems.append("credential or wallet file")
    return problems


def check_text(rel: str, data: bytes, patterns: list[re.Pattern]) -> list[str]:
    if rel in SCAN_EXEMPT or b"\x00" in data[:8192]:
        return []
    text = data.decode("utf-8", errors="ignore")
    problems = []
    # Report line numbers only: never echo the matched value.
    for pat in patterns:
        for m in pat.finditer(text):
            problems.append(f"patient-ID pattern /{pat.pattern}/ at line {text.count(chr(10), 0, m.start()) + 1}")
            break
    for m in TCKN.finditer(text):
        if valid_tckn(m.group()):
            problems.append(f"valid Turkish national ID number at line {text.count(chr(10), 0, m.start()) + 1}")
            break
    return problems


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())
    patterns = load_patterns(root)
    everything = "--all" in argv
    listing = (_git(root, "ls-files", "-z") if everything
               else _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"))
    files = [f for f in listing.decode().split("\0") if f]
    failures = []
    for rel in files:
        try:
            data = (root / rel).read_bytes() if everything else _git(root, "show", f":{rel}")
        except (OSError, subprocess.CalledProcessError):
            continue
        problems = check_path(rel, len(data)) + check_text(rel, data, patterns)
        failures += [f"  {rel}: {p}" for p in problems]
    if failures:
        print("BLOCKED by scripts/precommit_check.py:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        print("Remove these files or values. Do not bypass this check (no --no-verify).", file=sys.stderr)
        return 1
    print(f"precommit check passed ({len(files)} file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
