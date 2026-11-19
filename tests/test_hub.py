"""Tests for the hub. All fixtures are synthetic metadata; none came from a database."""
import csv
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.audit import dictionary  # noqa: E402
from src.audit.diff import diff  # noqa: E402
from src.common import suppress  # noqa: E402
from src.common.config import ConfigError, require  # noqa: E402
from src.db.base import get_adapter  # noqa: E402
from src.db.guard import ReadOnlyViolation, assert_read_only, identifier  # noqa: E402
from src.registry import registry  # noqa: E402
import precommit_check as pc  # noqa: E402


# ---- rule 1: small-cell suppression
@pytest.mark.parametrize("value,shown", [(0, "<10"), (9, "<10"), (10, "10"), ("1234", "1234"), ("", ""), (None, "")])
def test_count_suppression(value, shown):
    assert suppress.count(value) == shown


def test_completeness_never_reveals_small_counts():
    assert suppress.completeness(1000, 3) == ("<10", ">=99.1", "ok")
    assert suppress.completeness(1000, 995) == ("suppressed", "<=0.9", "under")
    assert suppress.completeness(1000, 950) == ("950", "5.0", "under")
    assert suppress.completeness(1000, 400) == ("400", "60.0", "ok")
    assert suppress.completeness(4, 1) == ("suppressed", "suppressed", "indeterminate")
    assert suppress.completeness(15, 2)[2] == "indeterminate"
    assert suppress.completeness("", "")[2] == "no_stats"


# ---- rule 2: read-only guard
@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM t", "with a as (select 1 from dual) select * from a;",
    "SELECT comments, 'DROP TABLE x' AS note FROM all_tab_comments -- delete",
])
def test_guard_allows_queries(sql):
    assert_read_only(sql)


@pytest.mark.parametrize("sql", [
    "DELETE FROM t", "SELECT 1 FROM dual; DROP TABLE t", "CREATE TABLE x AS SELECT * FROM t",
    "SELECT * FROM t FOR UPDATE", "BEGIN NULL; END;", "EXPLAIN PLAN FOR SELECT 1 FROM dual",
    "SELECT a INTO b FROM t", "WITH x AS (SELECT 1 FROM dual) UPDATE t SET a = 1", "ALTER SESSION SET x = 1",
    "MERGE INTO t USING s ON (1=1) WHEN MATCHED THEN UPDATE SET a = 1", "TRUNCATE TABLE t",
])
def test_guard_blocks_writes(sql):
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql)


def test_identifier_rejects_injection():
    assert identifier("HOSP_DATA") == "HOSP_DATA"
    with pytest.raises(ReadOnlyViolation):
        identifier("X' OR '1'='1")


# ---- adapters
def test_unset_values_stop_the_run():
    with pytest.raises(ConfigError):
        require("UNSET", "schema")
    oracle = get_adapter({"id": "x", "engine": "oracle", "schema": "UNSET", "connection": {"mode": "UNSET", "alias": "UNSET"}})
    with pytest.raises(ConfigError):
        oracle.dictionary_queries()


def test_oracle_dictionary_queries_are_read_only_and_avoid_data_values():
    oracle = get_adapter({"id": "x", "engine": "oracle", "schema": "hosp", "connection": {"mode": "saved", "alias": "a"}})
    queries = oracle.dictionary_queries()
    assert set(queries) == set(get_adapter({"engine": "fixture"}).dictionary_queries())
    for alternatives in queries.values():
        for sql in alternatives:
            assert_read_only(sql)
            low = sql.lower()
            assert "'HOSP'" in sql
            for banned in ("low_value", "high_value", "histogram", "endpoint"):
                assert banned not in low


@pytest.mark.parametrize("engine", ["postgresql", "sqlserver", "mysql"])
def test_stub_engines_fail_clearly(engine):
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        get_adapter({"id": "x", "engine": engine}).dictionary_queries()


# ---- dictionary audit end to end on the fixture
@pytest.fixture
def audit(tmp_path):
    reg = tmp_path / "databases.yaml"
    reg.write_text(yaml.safe_dump({"databases": [{"id": "fx", "engine": "fixture", "schema": "S",
                                                   "fixture_dir": str(ROOT / "tests/fixtures/dict")}]}))
    doc = dictionary.run("fx", "2026-01-03", registry=reg, results_root=tmp_path / "results", docs_root=tmp_path / "docs")
    return doc, tmp_path / "results" / "fx" / "2026-01-03"


def rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def test_audit_outputs(audit):
    doc, out = audit
    tables = {r["table"]: r for r in rows(out / "tables.csv")}
    assert tables["T_PERSON"]["num_rows_stats"] == "1000"
    assert tables["T_TINY"]["num_rows_stats"] == "<10"
    assert tables["T_NOSTATS"]["num_rows_stats"] == ""
    assert tables["T_EVENT"]["partition_key"] == "EVENT_DATE"
    assert tables["T_EVENT"]["bytes_on_disk"] == ""  # segments fixture absent: reported as unavailable
    cols = {(r["table"], r["column"]): r for r in rows(out / "columns.csv")}
    assert ("V_SOMEVIEW", "Z") not in cols
    assert cols[("T_PERSON", "SEX")]["num_nulls_stats"] == "<10"
    assert cols[("T_EVENT", "UNIT")]["completeness_flag"] == "under"
    under = {(r["table"], r["column"]) for r in rows(out / "columns_under_floor.csv") if r["completeness_flag"] == "under"}
    assert under == {("T_PERSON", "DEATH_DATE"), ("T_PERSON", "RARE_FLAG"), ("T_EVENT", "UNIT")}
    fk = rows(out / "foreign_keys.csv")[0]
    assert (fk["table"], fk["ref_table"], fk["ref_columns"]) == ("T_EVENT", "T_PERSON", "PERSON_ID")
    assert rows(out / "join_candidates.csv")[0]["column"] == "PERSON_ID"
    text = doc.read_text()
    assert "NOT AVAILABLE" in text and "GATE 1 list" in text


def test_no_small_count_in_any_output(audit):
    _, out = audit
    for name in ("tables.csv", "columns.csv", "columns_under_floor.csv"):
        for r in rows(out / name):
            for field in ("num_rows_stats", "num_nulls_stats", "stats_sample_size"):
                v = r.get(field, "")
                assert not (v.isdigit() and int(v) < 10), (name, r)


def test_diff_detects_changes(audit, tmp_path):
    _, old = audit
    new = tmp_path / "new"
    new.mkdir()
    for f in ("tables.csv", "columns.csv"):
        text = (old / f).read_text()
        (new / f).write_text(text.replace("T_EVENT,50000", "T_EVENT,90000").replace("T_TINY", "T_NEW"))
    changes = {(c["change"], c["table"]) for c in diff(old, new)}
    assert {("row_count", "T_EVENT"), ("table_added", "T_NEW"), ("table_dropped", "T_TINY")} <= changes


# ---- registries
def test_registries_valid_and_seeded():
    assert registry.validate() == []
    dbs, ideas, studies = registry.load()
    assert [d["id"] for d in dbs] == ["vivax-oracle-01"]
    assert [i["id"] for i in ideas] == ["P1", "P2", "P3", "P4", "P5", "P6"]
    assert all(i["status"] == "proposed" for i in ideas) and studies == []
    assert "P1" in registry.status()


def test_registry_rejects_credentials(tmp_path):
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry/databases.yaml").write_text(yaml.safe_dump({"databases": [{
        "id": "d", "engine": "oracle", "connection": {"alias": "a", "password": "x"}, "schema": "s", "owner": "o",
        "ethics": {}, "last_audit": None, "audit_path": None, "node_card_path": None}]}))
    (tmp_path / "registry/ideas.yaml").write_text("ideas: []\n")
    (tmp_path / "registry/studies.yaml").write_text("studies: []\n")
    assert any("credential" in e for e in registry.validate(tmp_path))


# ---- data-safety check
def make_tckn(first9="123456789"):
    d = [int(c) for c in first9]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    return first9 + str(d10) + str((sum(d) + d10) % 10)


def test_path_rules():
    assert pc.check_path("results/audit/x/tables.csv", 100) == []
    assert pc.check_path("PROVENANCE.csv", 100) == []
    assert pc.check_path("templates/study/PROVENANCE.csv", 100) == []
    assert pc.check_path("src/a.py", 100) == []
    for bad in ("data/x.parquet", "notes/export.csv", "dump/full.dmp", "x/backup.sql.gz", "wallet/cwallet.sso", ".env"):
        assert pc.check_path(bad, 100), bad
    assert pc.check_path("results/big.json", 6 * 1024 * 1024)


def test_text_rules():
    good = make_tckn()
    assert pc.valid_tckn(good) and not pc.valid_tckn(good[:-1] + str((int(good[-1]) + 1) % 10))
    assert pc.check_text("a.md", f"id {good}\n".encode(), [])
    assert pc.check_text("a.md", b"value 0.12345678901 and 20261119120000\n", []) == []
    import re
    hits = pc.check_text("a.md", b"ok\nPAT-0001234\n", [re.compile(r"PAT-\d{7}")])
    assert hits and "line 2" in hits[0] and "0001234" not in hits[0]


def test_repository_passes_its_own_check():
    out = subprocess.run([sys.executable, "scripts/precommit_check.py", "--all"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_sqlcl_logon_override_never_takes_a_password():
    from src.db.base import QueryFailed
    base = {"id": "x", "engine": "oracle", "schema": "hosp"}
    ok = get_adapter({**base, "connection": {"sqlcl_logon": "-name hosp_ro"}})
    assert ok._connect_args() == ["-name", "hosp_ro"]
    assert get_adapter({**base, "connection": {"sqlcl_logon": "/@hosp_ro"}})._connect_args() == ["/@hosp_ro"]
    with pytest.raises(QueryFailed, match="credentials"):
        get_adapter({**base, "connection": {"sqlcl_logon": "scott/tiger@db"}})._connect_args()
