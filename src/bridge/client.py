"""Client side of the bridge: send one query to the machine that can reach the database.

A request is a committed file, bridge/requests/<id>.sql. The bridge
(tools/vivax_bridge.py, running on that machine) checks it, runs it, filters
the output and commits results/bridge/<id>/. Every query and every result is
therefore in git history.

    python -m src.bridge.client --mode aggregate --group-size N \\
        --cost "T_EVENT: 2.1 GB, SAMPLE(1), about 30 s" --purpose "events per year" \\
        --sql-file sql/oracle/events_per_year.sql

Modes
    dictionary  reads data-dictionary views only
    aggregate   reads data tables; must aggregate, must name its group-size
                column; the bridge removes groups under 10
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ..common import runlog
from ..common.config import ROOT
from ..db.base import QueryFailed

TRAILER = ("\n\nCo-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>\n"
           "Claude-Session: https://claude.ai/code/session_011NAQ1mWzgVZi623pU6761r")


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


def _branch(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def assert_private(repo: Path = ROOT) -> None:
    """Refuse to send a request while the hub repository is publicly readable."""
    import urllib.error
    import urllib.request
    from ..common.config import UNSET, project
    slug = project().get("github_repo")
    if repo != ROOT or not slug or slug == UNSET:
        return
    try:
        req = urllib.request.Request(f"https://github.com/{slug}", method="HEAD",
                                     headers={"User-Agent": "vivax-bridge-client"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            public = resp.status == 200
    except (urllib.error.URLError, OSError):
        public = False  # not anonymously readable, or unreachable; the bridge checks again
    if public:
        raise QueryFailed(f"github.com/{slug} is PUBLIC: queries and results sent through the bridge "
                          f"would be published. The lead must make the repository private first.")


def enqueue(sql: str, mode: str, *, db: str = "", count_columns=(), group_size=(), cost: str = "",
            purpose: str = "", timeout_s: int = 300, repo: Path = ROOT, push: bool = True) -> str:
    """Write, commit and push one request. Returns its id."""
    if push:
        assert_private(repo)
    body = sql.strip().rstrip(";").strip()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    rid = f"{stamp}-{hashlib.sha256(body.encode()).hexdigest()[:8]}"
    header = {"db": db, "mode": mode, "purpose": purpose, "cost": cost,
              "count_columns": ", ".join(count_columns), "group_size": ", ".join(group_size),
              "timeout_s": str(timeout_s)}
    text = "".join(f"-- {k}: {' '.join(str(v).split())}\n" for k, v in header.items() if v) + "\n" + body + "\n"
    rel = f"bridge/requests/{rid}.sql"
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", "--", rel)
    _git(repo, "commit", "--quiet", "-m", f"bridge request {rid}: {purpose or mode}{TRAILER}", "--", rel)
    if push:
        branch = _branch(repo)
        for attempt in range(4):
            if _git(repo, "push", "--quiet", "-u", "origin", branch, check=False).returncode == 0:
                break
            time.sleep(2 ** (attempt + 1))
            # The bridge may have pushed results meanwhile: merge, do not rebase.
            _git(repo, "fetch", "--quiet", "origin", branch, check=False)
            _git(repo, "merge", "--quiet", "--no-edit", "FETCH_HEAD", check=False)
        else:
            raise QueryFailed("could not push the bridge request")
    return rid


def collect(rid: str, *, wait_s: int = 900, poll_s: int = 10, repo: Path = ROOT) -> tuple[dict, str]:
    """Wait for the bridge's answer. Returns (meta, result_csv_text). Reads from the remote branch."""
    branch = _branch(repo)
    deadline = time.time() + wait_s
    while True:
        _git(repo, "fetch", "--quiet", "origin", branch, check=False)
        meta = _git(repo, "show", f"origin/{branch}:results/bridge/{rid}/meta.json", check=False)
        if meta.returncode == 0:
            info = json.loads(meta.stdout)
            if info.get("status") != "ok":
                raise QueryFailed(f"bridge refused {rid}: {info.get('reason', 'no reason given')}")
            data = _git(repo, "show", f"origin/{branch}:results/bridge/{rid}/result.csv")
            return info, data.stdout
        if time.time() >= deadline:
            raise QueryFailed(f"no answer for {rid} after {wait_s}s. Is the bridge running, on the VPN, "
                              f"and (for aggregate queries) waiting for a 'y' at its terminal?")
        time.sleep(poll_s)


def query(sql: str, mode: str, **kw) -> tuple[dict, str]:
    wait_s, poll_s, repo = kw.pop("wait_s", 900), kw.pop("poll_s", 10), kw.get("repo", ROOT)
    rid = enqueue(sql, mode, **kw)
    return collect(rid, wait_s=wait_s, poll_s=poll_s, repo=repo)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Send one query through the bridge")
    ap.add_argument("--mode", required=True, choices=["dictionary", "aggregate"])
    ap.add_argument("--sql-file", required=True)
    ap.add_argument("--db", default="")
    ap.add_argument("--group-size", default="", help="comma-separated; required in aggregate mode")
    ap.add_argument("--count-columns", default="")
    ap.add_argument("--cost", default="", help="cost estimate; required in aggregate mode (rule 3)")
    ap.add_argument("--purpose", default="")
    ap.add_argument("--timeout-s", type=int, default=300)
    ap.add_argument("--wait-s", type=int, default=900)
    args = ap.parse_args(argv)
    split = lambda s: [c.strip() for c in s.split(",") if c.strip()]  # noqa: E731
    sql = Path(args.sql_file).read_text(encoding="utf-8")
    cmd = "python -m src.bridge.client " + " ".join(argv if argv is not None else sys.argv[1:])
    with runlog.logged(cmd, "results/bridge/", note=f"cost estimate: {args.cost or 'dictionary only'}"):
        meta, _ = query(sql, args.mode, db=args.db, count_columns=split(args.count_columns),
                        group_size=split(args.group_size), cost=args.cost, purpose=args.purpose,
                        timeout_s=args.timeout_s, wait_s=args.wait_s)
    print(f"ok: results/bridge/{meta['id']}/result.csv  rows={meta.get('rows')}  "
          f"small groups removed={meta.get('groups_removed')}")
    print("Run 'git pull' (merge) to bring the result file into the working tree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
