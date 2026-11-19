"""Tests for the bridge. A fake `sql` executable serves synthetic CSVs; no database is contacted."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("vivax_bridge", ROOT / "tools" / "vivax_bridge.py")
vb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vb)

from src.bridge import client  # noqa: E402
from src.db.base import QueryFailed, get_adapter  # noqa: E402
from src.db.guard import ReadOnlyViolation, assert_read_only  # noqa: E402

AGG = {"mode": "aggregate", "group_size": "N", "cost": "small"}


def req(sql, **head):
    return {"sql": sql, **head}


# ---- request checks
@pytest.mark.parametrize("sql,head", [
    ("SELECT table_name, num_rows FROM all_tables WHERE owner = '{SCHEMA}'", {"mode": "dictionary"}),
    ("SELECT c.table_name FROM all_tab_columns c LEFT JOIN all_tables t ON t.table_name = c.table_name", {"mode": "dictionary"}),
    ("SELECT code, COUNT(*) AS n FROM {SCHEMA}.t_event GROUP BY code", AGG),
    ("SELECT COUNT(*) AS n FROM {SCHEMA}.t_event SAMPLE (1)", AGG),
])
def test_bridge_accepts(sql, head):
    vb.check_request(req(sql, **head))


@pytest.mark.parametrize("sql,head,why", [
    ("SELECT * FROM {SCHEMA}.t_event", {"mode": "dictionary"}, "not on the list"),
    ("SELECT * FROM all_tables, {SCHEMA}.t_event", {"mode": "dictionary"}, "comma"),
    ("SELECT low_value FROM all_tab_columns", {"mode": "dictionary"}, "real data values"),
    ("SELECT * FROM all_tab_col_statistics", {"mode": "dictionary"}, "not on the list"),
    ("SELECT * FROM {SCHEMA}.t_event", AGG, "aggregate function"),
    ("SELECT code, COUNT(*) n FROM t GROUP BY code", {"mode": "aggregate", "cost": "x"}, "group_size"),
    ("SELECT code, COUNT(*) n FROM t GROUP BY code", {"mode": "aggregate", "group_size": "N"}, "cost"),
    ("SELECT COUNT(*) n FROM t@remote", AGG, "links"),
    ("SELECT UTL_HTTP.REQUEST('http://x') , COUNT(*) n FROM t", AGG, "packages"),
    ("DELETE FROM t", AGG, "SELECT"),
    ("SELECT COUNT(*) n FROM t; DROP TABLE t", AGG, "one statement"),
    ("EXPLAIN PLAN FOR SELECT COUNT(*) FROM t", AGG, "SELECT"),
    ("SELECT COUNT(*) n FROM t", {"mode": "rows"}, "mode"),
])
def test_bridge_refuses(sql, head, why):
    with pytest.raises(vb.Refused, match=why):
        vb.check_request(req(sql, **head))


@pytest.mark.parametrize("sql", ["DELETE FROM t", "SELECT 1 FROM dual; DROP TABLE t", "SELECT a INTO b FROM t",
                                 "SELECT * FROM t FOR UPDATE", "BEGIN NULL; END;"])
def test_bridge_guard_agrees_with_repo_guard(sql):
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql)
    with pytest.raises(vb.Refused):
        vb.check_request(req(sql, **AGG))


def test_oracle_dictionary_queries_pass_the_bridge():
    oracle = get_adapter({"id": "x", "engine": "oracle", "schema": "UNSET", "connection": {"transport": "bridge"}})
    for alternatives in oracle.dictionary_queries().values():
        for sql in alternatives:
            assert "{SCHEMA}" in sql
            vb.check_request(req(assert_read_only(sql), mode="dictionary"))


def test_request_header_roundtrip():
    r = vb.parse_request("-- mode: aggregate\n-- group_size: N\n-- cost: 2 GB, 30 s\n\nSELECT COUNT(*) n\n-- inner\nFROM t;\n")
    assert (r["mode"], r["group_size"], r["cost"]) == ("aggregate", "N", "2 GB, 30 s")
    assert r["sql"].startswith("SELECT") and r["sql"].endswith("FROM t")


# ---- result filter
FX = ROOT / "tests/fixtures/bridge"


def test_small_groups_removed_and_counts_suppressed():
    r = req("SELECT code, COUNT(*) n, COUNT(DISTINCT p) n_patients FROM t GROUP BY code",
            mode="aggregate", group_size="N", count_columns="N_PATIENTS")
    header, rows, stats = vb.filter_result(FX / "agg.csv", r, vb.DEFAULT_ID_COLUMNS)
    assert header == ["CODE", "N", "N_PATIENTS"]
    assert rows == [["I10", "5200", "900"], ["E11", "340", "<10"], ["J45", "12", "12"]]
    assert stats == {"rows": 3, "groups_removed": 1}


def test_free_text_and_identifiers_refused():
    r = req("SELECT note, COUNT(*) n FROM t GROUP BY note", mode="aggregate", group_size="N")
    with pytest.raises(vb.Refused, match="longer than"):
        vb.filter_result(FX / "notes.csv", r, vb.DEFAULT_ID_COLUMNS)
    with pytest.raises(vb.Refused, match="identifier"):
        vb.filter_result(FX / "ids.csv", r, vb.DEFAULT_ID_COLUMNS)


def test_setup_rejects_password_shapes():
    import re
    assert re.search(r"[^/\s@]+/[^@\s]+", "scott/tiger@db")
    assert not re.search(r"[^/\s@]+/[^@\s]+", "/@alias") and not re.search(r"[^/\s@]+/[^@\s]+", "-name conn")


# ---- end to end over git, with the fake SQLcl
@pytest.fixture
def world(tmp_path, monkeypatch):
    def sh(*a, cwd=None):
        subprocess.run(a, cwd=cwd, check=True, capture_output=True)
    origin, cloud, home = tmp_path / "origin.git", tmp_path / "cloud", tmp_path / "bridge_home"
    sh("git", "init", "--bare", "-b", "main", str(origin))
    sh("git", "clone", str(origin), str(cloud))
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        sh("git", "config", k, v, cwd=cloud)
    (cloud / "README.md").write_text("x\n")
    sh("git", "add", "-A", cwd=cloud)
    sh("git", "commit", "-m", "init", cwd=cloud)
    sh("git", "push", "-u", "origin", "main", cwd=cloud)
    home.mkdir()
    (home / "config.json").write_text(json.dumps({
        "repo": str(origin), "branch": "main", "logon": "-name test", "schema": "HOSP",
        "allow_unverified_visibility": True}))
    env = {**os.environ, "VIVAX_BRIDGE_HOME": str(home), "FAKE_SQL_FIXTURES": str(FX),
           "PATH": f"{ROOT / 'tests/fake_bin'}{os.pathsep}{os.environ['PATH']}"}

    def bridge_once():
        return subprocess.run([sys.executable, str(ROOT / "tools/vivax_bridge.py"), "run", "--auto", "--once"],
                              env=env, capture_output=True, text=True)
    return cloud, bridge_once, home


def test_round_trip(world):
    cloud, bridge_once, home = world
    ok = client.enqueue("SELECT code, COUNT(*) AS n, COUNT(DISTINCT pid) AS n_patients FROM {SCHEMA}.t_event GROUP BY code",
                        "aggregate", group_size=["N"], count_columns=["N_PATIENTS"], cost="tiny", purpose="test", repo=cloud)
    bad = client.enqueue("SELECT * FROM {SCHEMA}.t_event", "dictionary", repo=cloud)
    gone = client.enqueue("SELECT COUNT(*) AS n FROM {SCHEMA}.t_absent", "aggregate", group_size=["N"], cost="tiny", repo=cloud)
    run = bridge_once()
    assert run.returncode == 0, run.stderr
    meta, text = client.collect(ok, wait_s=0, repo=cloud)
    assert meta["rows"] == 3 and meta["groups_removed"] == 1
    assert "Z99" not in text and "E11,340,<10" in text
    with pytest.raises(QueryFailed, match="not on the list"):
        client.collect(bad, wait_s=0, repo=cloud)
    with pytest.raises(QueryFailed, match="ORA-00942"):
        client.collect(gone, wait_s=0, repo=cloud)
    log = (home / "bridge.log").read_text()
    assert ok in log and "I10" not in log
    assert bridge_once().stdout.count(" ok ") == 0  # nothing is run twice


def test_bridge_stops_on_public_repository(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    (home / "config.json").write_text(json.dumps({"repo": "https://example.invalid/x/y.git", "branch": "main",
                                                  "logon": "-name t", "schema": "S"}))
    run = subprocess.run([sys.executable, str(ROOT / "tools/vivax_bridge.py"), "run", "--once"],
                         env={**os.environ, "VIVAX_BRIDGE_HOME": str(home)}, capture_output=True, text=True)
    assert run.returncode != 0 and "could not confirm" in run.stderr


def test_dictionary_audit_through_the_bridge(world, tmp_path, monkeypatch):
    """The whole Phase 1 step 1 audit, every query travelling cloud -> git -> bridge -> git -> cloud."""
    import yaml
    from src.audit import dictionary
    cloud, _, home = world
    monkeypatch.setenv("FAKE_SQL_FIXTURES", str(ROOT / "tests/fixtures/dict"))
    env = {**os.environ, "VIVAX_BRIDGE_HOME": str(home),
           "PATH": f"{ROOT / 'tests/fake_bin'}{os.pathsep}{os.environ['PATH']}"}
    bridge = subprocess.Popen([sys.executable, str(ROOT / "tools/vivax_bridge.py"), "run", "--auto", "--poll", "0.3"],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        reg = tmp_path / "databases.yaml"
        reg.write_text(yaml.safe_dump({"databases": [{
            "id": "viabridge", "engine": "oracle", "schema": "UNSET", "connection": {"transport": "bridge"},
            "bridge_client_options": {"repo": str(cloud), "poll_s": 0.3, "wait_s": 60}}]}))
        doc = dictionary.run("viabridge", "2026-01-04", registry=reg,
                             results_root=tmp_path / "results", docs_root=tmp_path / "docs")
    finally:
        bridge.terminate()
        bridge.wait(timeout=10)
    out = tmp_path / "results/viabridge/2026-01-04"
    import csv
    tables = {r["table"]: r for r in csv.DictReader(open(out / "tables.csv"))}
    assert tables["T_PERSON"]["num_rows_stats"] == "1000" and tables["T_TINY"]["num_rows_stats"] == "<10"
    cols = {(r["table"], r["column"]): r for r in csv.DictReader(open(out / "columns.csv"))}
    assert cols[("T_PERSON", "SEX")]["num_nulls_stats"] == "<10"
    assert cols[("T_EVENT", "UNIT")]["completeness_flag"] == "under"
    manifest = json.loads((out / "manifest.json").read_text())["queries"]
    assert manifest["segments"]["status"] == "unavailable" and manifest["tables"]["status"] == "ok"
    # the raw small count never reached git: the bridge suppressed it before committing
    shown = subprocess.run(["git", "-C", str(cloud), "log", "-p", "origin/main", "--", "results/bridge"],
                           capture_output=True, text=True).stdout
    assert "T_TINY,<10" in shown and "T_TINY,4," not in shown
    assert "GATE 1 list" in doc.read_text()
