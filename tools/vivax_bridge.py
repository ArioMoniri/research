#!/usr/bin/env python3
"""Vivax bridge: lets a remote Claude session query the database through this machine.

One file, Python standard library only. Run it on a machine that can reach
the database (for example a Mac on the hospital VPN):

    python3 vivax_bridge.py setup     # once: asks for the SQLcl connection name and schema
    python3 vivax_bridge.py run       # serve requests until Ctrl-C

How it works
    The remote session commits a query to  bridge/requests/<id>.sql  in the
    private GitHub repository. This program polls the repository, checks the
    query, runs it with SQLcl, filters the output, and commits the filtered
    result to  results/bridge/<id>/ . Nothing listens for inbound connections
    and no VPN or database credential leaves this machine.

What it enforces (defence in depth; the remote session is bound by the same rules)
    * Read-only: a single SELECT or WITH statement. No DDL, DML, PL/SQL, locks,
      database links or network packages.
    * Two modes only.
      dictionary: every table read must be a data-dictionary view on a fixed
        list; statistics columns that hold real values are refused.
      aggregate: the query must aggregate and must name its group-size column.
        Groups smaller than 10 are removed; other counts under 10 become "<10".
    * Output limits: at most 5000 rows, cells at most 120 characters, no
      identifier-like column names, no valid Turkish national ID numbers.
      A result that breaks a limit is refused whole, never truncated.
    * It executes SQL only. It never runs code from the repository and never
      updates itself.
    * It refuses to run while the GitHub repository is public.
    * No password is asked for, stored or passed. If SQLcl would prompt for
      one, the query fails.

Files it keeps:  ~/.vivax-bridge/config.json (connection name, schema),
~/.vivax-bridge/repo (a small working copy of the repository: code, no data),
~/.vivax-bridge/bridge.log (request ids, status, durations; never row content).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1"
HOME = Path(os.environ.get("VIVAX_BRIDGE_HOME", Path.home() / ".vivax-bridge"))
DEFAULT_REPO = "https://github.com/ArioMoniri/research.git"
DEFAULT_BRANCH = "claude/blissful-albattani-s5krm7"

THRESHOLD = 10
MAX_ROWS = 5000
MAX_CELL = 120
MAX_TIMEOUT_S = 600          # project rule 3: nothing over ten minutes without the lead
FORBIDDEN = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "CREATE", "ALTER", "DROP", "TRUNCATE",
    "RENAME", "GRANT", "REVOKE", "COMMENT", "PURGE", "FLASHBACK", "CALL", "EXEC", "EXECUTE",
    "BEGIN", "DECLARE", "LOCK", "COMMIT", "ROLLBACK", "SAVEPOINT", "ANALYZE", "AUDIT",
    "NOAUDIT", "COPY", "HOST", "EXPLAIN",
}
DICTIONARY_VIEWS = {
    f"{p}_{v}" for p in ("ALL", "USER", "DBA") for v in (
        "TABLES", "TAB_COLUMNS", "TAB_COLS", "TAB_COMMENTS", "COL_COMMENTS", "SEGMENTS",
        "PART_TABLES", "PART_KEY_COLUMNS", "TAB_PARTITIONS", "CONSTRAINTS", "CONS_COLUMNS",
        "INDEXES", "IND_COLUMNS", "VIEWS", "MVIEWS", "OBJECTS", "TAB_STATISTICS", "TABLESPACES")
} | {"DUAL"}
# Dictionary columns that hold real data values.
VALUE_COLUMNS = re.compile(r"\b(LOW_VALUE|HIGH_VALUE|ENDPOINT_\w+|DATA_DEFAULT)\b", re.I)
AGGREGATE = re.compile(
    r"\b(COUNT|SUM|AVG|MIN|MAX|MEDIAN|STDDEV|VARIANCE|PERCENTILE_CONT|PERCENTILE_DISC|"
    r"APPROX_COUNT_DISTINCT|APPROX_MEDIAN|APPROX_PERCENTILE)\s*\(", re.I)
DEFAULT_ID_COLUMNS = (r"(patient|hasta|person|subject|kisi).*(id|no|key|kod)|^tc|kimlik|^mrn$|"
                      r"protokol|protocol|dosya_?no|^name$|^ad$|soyad|surname|adres|address|"
                      r"telefon|phone|e_?mail|note_?text|^rowid$")
TCKN = re.compile(r"(?<![\d.])[1-9]\d{10}(?!\d)")
ERR = re.compile(r"\b(ORA-\d{5}|SP2-\d{4}|SQLcl-\d+|PLS-\d{5})\b")
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")
REQ_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,80}$")


class Refused(Exception):
    """The request or its result broke a rule. The message never contains row content."""


# ------------------------------------------------------------------ request checks
def strip_literals(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def parse_request(text: str) -> dict:
    """Leading '-- key: value' lines are the header; the rest is the query."""
    head, body, in_head = {}, [], True
    for line in text.splitlines():
        m = re.match(r"^\s*--\s*([a-z_]+)\s*:\s*(.*?)\s*$", line) if in_head else None
        if m:
            head[m.group(1)] = m.group(2)
        elif in_head and line.strip() == "":
            continue
        else:
            in_head = False
            body.append(line)
    head["sql"] = "\n".join(body).strip().rstrip(";").strip()
    return head


def check_request(req: dict) -> None:
    sql, mode = req.get("sql", ""), req.get("mode", "")
    bare = strip_literals(sql)
    if mode not in ("dictionary", "aggregate"):
        raise Refused("header 'mode' must be dictionary or aggregate")
    if ";" in bare:
        raise Refused("more than one statement")
    first = re.match(r"\s*\(*\s*([A-Za-z]+)", bare)
    if not first or first.group(1).upper() not in ("SELECT", "WITH"):
        raise Refused("only SELECT or WITH queries are allowed")
    hit = sorted(set(re.findall(r"[A-Za-z_]+", bare.upper())) & FORBIDDEN)
    if hit:
        raise Refused(f"forbidden keyword(s): {', '.join(hit)}")
    if re.search(r"\bFOR\s+UPDATE\b|\bINTO\b", bare, re.I):
        raise Refused("FOR UPDATE and INTO are not allowed")
    if re.search(r"\b(DBMS|UTL|OWA|HTP)_\w+|\bHTTPURITYPE\b|\bXMLTYPE\b", bare, re.I):
        raise Refused("database packages are not allowed")
    if "@" in bare:
        raise Refused("database links are not allowed")
    if VALUE_COLUMNS.search(bare):
        raise Refused("statistics columns that hold real data values are not allowed")
    if mode == "dictionary":
        if re.search(r"\bFROM\s+[\w$#.\"]+(\s+\w+)?\s*,", bare, re.I):
            raise Refused("dictionary mode: use explicit JOIN, not comma joins")
        for obj in re.findall(r"\b(?:FROM|JOIN)\s+(\(|[\w$#.\"{}]+)", bare, re.I):
            if obj == "(":
                continue
            name = obj.replace('"', "").upper()
            name = name[4:] if name.startswith("SYS.") else name
            if name not in DICTIONARY_VIEWS:
                raise Refused(f"dictionary mode: '{name}' is not on the list of dictionary views")
    else:
        if not AGGREGATE.search(bare):
            raise Refused("aggregate mode: the query must use an aggregate function")
        if not columns_of(req, "group_size"):
            raise Refused("aggregate mode: header 'group_size' must name the column holding each group's size")
        if not req.get("cost"):
            raise Refused("aggregate mode: header 'cost' must state the estimated cost (project rule 3)")


def columns_of(req: dict, key: str) -> list[str]:
    return [c.strip().upper() for c in req.get(key, "").split(",") if c.strip()]


def timeout_of(req: dict) -> int:
    try:
        return max(5, min(int(req.get("timeout_s", 300)), MAX_TIMEOUT_S))
    except ValueError:
        return 300


# ------------------------------------------------------------------ result filter
def valid_tckn(s: str) -> bool:
    d = [int(c) for c in s]
    if ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


def as_int(text: str):
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def filter_result(raw: Path, req: dict, id_columns: str) -> tuple[list[str], list[list[str]], dict]:
    """Apply the output rules. Returns (header, rows, stats) or raises Refused."""
    with open(raw, newline="", encoding="utf-8-sig") as fh:
        table = list(csv.reader(fh))
    if not table:
        return [], [], {"rows": 0, "groups_removed": 0}
    header = [h.strip().upper() for h in table[0]]
    body = [r for r in table[1:] if any(c.strip() for c in r)]
    banned = re.compile(id_columns, re.I)
    for h in header:
        if banned.search(h):
            raise Refused(f"output column '{h}' looks like an identifier or free text")
    counts = set(columns_of(req, "count_columns"))
    group = columns_of(req, "group_size")
    grouped = bool(re.search(r"\bGROUP\s+BY\b", strip_literals(req["sql"]), re.I))
    if req["mode"] == "aggregate":
        missing = [c for c in group if c not in header]
        if missing:
            raise Refused(f"group_size column(s) not in the output: {', '.join(missing)}")
    gi = [header.index(c) for c in group if c in header]
    ci = [i for i, h in enumerate(header) if h in counts or i in gi]
    out, removed = [], 0
    for row in body:
        if len(row) != len(header):
            raise Refused("malformed CSV row")
        row = [c.strip() for c in row]
        small = any((as_int(row[i]) if as_int(row[i]) is not None else 0) < THRESHOLD for i in gi)
        if small and grouped:
            removed += 1          # a small group's key can itself identify someone
            continue
        for i in ci:
            n = as_int(row[i])
            if n is not None and n < THRESHOLD:
                row[i] = f"<{THRESHOLD}"
        for cell in row:
            if len(cell) > MAX_CELL:
                raise Refused(f"a cell is longer than {MAX_CELL} characters (free text is not allowed)")
            for m in TCKN.finditer(cell):
                if valid_tckn(m.group()):
                    raise Refused("the output contains a valid Turkish national ID number")
        out.append(row)
    if len(out) > MAX_ROWS:
        raise Refused(f"{len(out)} rows after filtering; the limit is {MAX_ROWS}. Aggregate further.")
    return header, out, {"rows": len(out), "groups_removed": removed}


# ------------------------------------------------------------------ SQLcl
def run_sqlcl(cfg: dict, sql: str, out: Path, timeout_s: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "q.sql"
        script.write_text(
            "WHENEVER SQLERROR EXIT FAILURE\nWHENEVER OSERROR EXIT FAILURE\n"
            "SET TERMOUT OFF\nSET FEEDBACK OFF\nSET ECHO OFF\nSET VERIFY OFF\nSET SQLFORMAT csv\n"
            f'SPOOL "{out}"\n{sql};\nSPOOL OFF\nEXIT\n', encoding="utf-8")
        cmd = [cfg.get("sqlcl", "sql"), "-S", "-L", *cfg["logon"].split(), f"@{script}"]
        try:
            proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout_s)
        except FileNotFoundError:
            raise Refused("SQLcl ('sql') was not found on this machine")
        except subprocess.TimeoutExpired:
            raise Refused(f"the query ran longer than {timeout_s}s and was stopped")
    codes = sorted(set(ERR.findall((proc.stdout or "") + (proc.stderr or ""))))
    if proc.returncode != 0 or codes or not out.exists():
        raise Refused(f"SQLcl failed (exit {proc.returncode}; codes: {', '.join(codes) or 'none reported'}). "
                      "If it needs a password, save the connection in SQLcl first; this program never handles one.")


# ------------------------------------------------------------------ git transport
def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=vivax-bridge",
                           "-c", "user.email=vivax-bridge@localhost", *args],
                          capture_output=True, text=True, check=check)


def repo_is_public(url: str) -> bool | None:
    """True if an anonymous request can see the repository. None if it cannot be determined."""
    m = re.match(r"^https://github\.com/([^/]+)/([^/]+?)(\.git)?/?$", url)
    if not m:
        return None
    try:
        req = urllib.request.Request(f"https://github.com/{m.group(1)}/{m.group(2)}", method="HEAD",
                                     headers={"User-Agent": "vivax-bridge"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        return False if exc.code == 404 else None
    except (urllib.error.URLError, OSError):
        return None


def require_private(cfg: dict) -> None:
    state = repo_is_public(cfg["repo"])
    if state is True:
        sys.exit("STOP: the GitHub repository is PUBLIC. Queries and results would be published.\n"
                 "Make it private (GitHub > Settings > General > Danger Zone > Change visibility), then run again.")
    if state is None and not cfg.get("allow_unverified_visibility"):
        sys.exit("STOP: could not confirm that the repository is private (network error or a non-GitHub URL).")


def sync(cfg: dict, repo: Path) -> None:
    if not (repo / ".git").exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", "--branch", cfg["branch"], "--single-branch",
                        cfg["repo"], str(repo)], check=True)
    git(repo, "fetch", "--quiet", "origin", cfg["branch"])
    git(repo, "reset", "--quiet", "--hard", f"origin/{cfg['branch']}")


def publish(cfg: dict, repo: Path, rel: str, message: str) -> None:
    git(repo, "add", "--", rel)
    git(repo, "commit", "--quiet", "-m", message, "--", rel)
    for attempt in range(4):
        if git(repo, "push", "--quiet", "origin", f"HEAD:{cfg['branch']}", check=False).returncode == 0:
            return
        time.sleep(2 ** attempt)
        git(repo, "pull", "--quiet", "--rebase", "origin", cfg["branch"], check=False)
    raise RuntimeError("could not push the result after four attempts")


# ------------------------------------------------------------------ main loop
def log(line: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"{stamp}  {line}", flush=True)
    HOME.mkdir(parents=True, exist_ok=True)
    with open(HOME / "bridge.log", "a", encoding="utf-8") as fh:
        fh.write(f"{stamp}  {line}\n")


def handle(cfg: dict, repo: Path, path: Path, auto: bool) -> None:
    rid = path.stem
    out_dir = repo / "results" / "bridge" / rid
    text = path.read_text(encoding="utf-8")
    meta = {"id": rid, "bridge_version": VERSION, "sql_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "received": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    start = time.time()
    try:
        if not REQ_ID.match(rid):
            raise Refused("bad request id")
        req = parse_request(text)
        meta.update(mode=req.get("mode"), purpose=req.get("purpose", ""), cost=req.get("cost", ""))
        check_request(req)
        if req["mode"] == "aggregate" and not auto:
            print("\n" + "=" * 72 + f"\nRequest {rid} wants to read data tables (aggregate mode).\n"
                  f"Purpose: {req.get('purpose', '(none given)')}\nEstimated cost: {req['cost']}\n"
                  + "-" * 72 + f"\n{req['sql']}\n" + "=" * 72)
            if input("Run it? [y/N] ").strip().lower() != "y":
                raise Refused("declined by the operator at the bridge")
        sql = req["sql"].replace("{SCHEMA}", cfg["schema"])
        with tempfile.TemporaryDirectory() as tmp:      # raw output never leaves this directory
            raw = Path(tmp) / "raw.csv"
            run_sqlcl(cfg, sql, raw, timeout_of(req))
            header, rows, stats = filter_result(raw, req, cfg.get("id_columns", DEFAULT_ID_COLUMNS))
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "result.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)
        meta.update(status="ok", **stats)
    except Refused as exc:
        meta.update(status="refused", reason=str(exc))
    meta["duration_s"] = round(time.time() - start, 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    publish(cfg, repo, f"results/bridge/{rid}", f"bridge: {rid} {meta['status']}")
    log(f"{rid}  {meta['status']}  {meta['duration_s']}s  "
        + (f"rows={meta.get('rows')} removed={meta.get('groups_removed')}" if meta["status"] == "ok" else meta["reason"]))


def pending(repo: Path) -> list[Path]:
    reqs = sorted((repo / "bridge" / "requests").glob("*.sql"))
    return [p for p in reqs if not (repo / "results" / "bridge" / p.stem / "meta.json").exists()]


def load_config() -> dict:
    path = HOME / "config.json"
    if not path.exists():
        sys.exit("Not set up yet. Run:  python3 vivax_bridge.py setup")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_run(args) -> int:
    cfg = load_config()
    require_private(cfg)
    repo = HOME / "repo"
    log(f"bridge v{VERSION} serving {cfg['repo']} [{cfg['branch']}]  "
        f"aggregate queries: {'automatic' if args.auto else 'ask before each'}")
    checked = time.time()
    while True:
        try:
            if time.time() - checked > 600:
                require_private(cfg)
                checked = time.time()
            sync(cfg, repo)
            for path in pending(repo):
                handle(cfg, repo, path, args.auto)
        except KeyboardInterrupt:
            log("stopped")
            return 0
        except (subprocess.CalledProcessError, RuntimeError, OSError) as exc:
            log(f"transport problem, will retry: {type(exc).__name__}")
        if args.once:
            return 0
        try:
            time.sleep(args.poll)
        except KeyboardInterrupt:
            log("stopped")
            return 0


def cmd_test(args) -> int:
    cfg = load_config()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "t.csv"
        try:
            run_sqlcl(cfg, "SELECT 1 AS ok FROM dual", out, 60)
        except Refused as exc:
            print(f"FAILED: {exc}")
            return 1
        rows = list(csv.reader(open(out, newline="", encoding="utf-8-sig")))
    if len(rows) == 2 and rows[1][0].strip() == "1":
        print("Database connection works, with no password prompt.")
        return 0
    print("Connected, but the output was not in the expected CSV form. Check the SQLcl version.")
    return 1


def cmd_setup(args) -> int:
    HOME.mkdir(parents=True, exist_ok=True)
    print("Vivax bridge setup. No password is asked for or stored.\n")

    def ask(prompt, default=""):
        answer = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
        return answer or default

    cfg = {"repo": ask("GitHub repository URL", DEFAULT_REPO), "branch": ask("Branch", DEFAULT_BRANCH)}
    print("\nHow SQLcl connects. Give the arguments that follow 'sql' on the command line,\n"
          "for example  -name my_saved_connection   or   /@my_wallet_alias")
    cfg["logon"] = ask("SQLcl logon arguments")
    if re.search(r"[^/\s@]+/[^@\s]+", cfg["logon"]) or not re.match(r"^[A-Za-z0-9_.\-/@ ]+$", cfg["logon"]):
        sys.exit("That looks like it contains a password or unexpected characters. Nothing was saved.")
    cfg["schema"] = ask("Schema that holds the patient tables").upper()
    if not IDENT.match(cfg["schema"]):
        sys.exit("That is not a valid schema name. Nothing was saved.")
    path = HOME / "config.json"
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"\nSaved {path}\nTesting the connection...")
    return cmd_test(args)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vivax database bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="one-time configuration").set_defaults(fn=cmd_setup)
    sub.add_parser("test", help="check the database connection").set_defaults(fn=cmd_test)
    run = sub.add_parser("run", help="serve requests until Ctrl-C")
    run.add_argument("--auto", action="store_true", help="do not ask before each aggregate query")
    run.add_argument("--once", action="store_true", help="process what is pending, then exit")
    run.add_argument("--poll", type=float, default=15, help="seconds between checks")
    run.set_defaults(fn=cmd_run)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
